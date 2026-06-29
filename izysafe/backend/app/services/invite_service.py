"""Guardian invites: create (with tier/duplicate guards) + accept (strict phone match)."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import APIException
from app.core.validators import validate_phone
from app.models.child import Child, FamilyMember, Invite
from app.models.user import User
from app.services.children_service import ChildrenService, effective_tier
from app.services.invite_gateway import InviteGateway

# Guardians (non-primary members) allowed per child, by tier. None = unlimited.
GUARDIAN_LIMITS: dict[str, int | None] = {"free": 0, "basic": 2, "premium": 5, "school": None}

_UPGRADE_MSG = {
    "free": "Upgrade to Basic plan to add guardians for this child",
    "basic": "Upgrade to Premium plan to add up to 5 guardians per child",
}


class InviteService:
    def __init__(self, db: AsyncSession, gateway: InviteGateway) -> None:
        self.db = db
        self.gateway = gateway

    # ----------------------------------------------------------------- create
    async def create_invite(
        self, inviter: User, child_id: uuid.UUID, data: dict[str, Any]
    ) -> tuple[Invite, str | None]:
        # Inviter must be able to manage this child (404 if not a member, 403 if no manage).
        child, _, _ = await ChildrenService(self.db).get_child(inviter, child_id, require="manage")

        phone = validate_phone(data["phone"])
        if phone == inviter.phone:
            raise APIException(400, "CANNOT_INVITE_SELF", "You cannot invite your own number")

        await self._guard_already_member(child_id, phone)
        await self._guard_duplicate_pending(child_id, phone)
        await self._enforce_guardian_limit(child_id)

        token = secrets.token_hex(32)
        invite = Invite(
            child_id=child_id,
            invited_by=inviter.id,
            phone=phone,
            role=data.get("role", "guardian"),
            can_view=data.get("can_view", True),
            can_call=data.get("can_call", False),
            can_manage=data.get("can_manage", False),
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.invite_expiry_hours),
        )
        self.db.add(invite)
        await self.db.commit()
        await self.db.refresh(invite)

        # Delivery is best-effort: a failure still returns a shareable link.
        link = f"{settings.invite_base_url}/{token}"
        message = (
            f"{inviter.name or 'A parent'} invited you to help keep {child.name} safe on "
            f"IzySafe. Tap to accept: {link}"
        )
        channel = await self.gateway.send_invite(phone, message)
        return invite, channel

    # ----------------------------------------------------------------- accept
    async def accept_invite(self, user: User, token: str) -> tuple[Child, FamilyMember]:
        invite = (
            await self.db.execute(select(Invite).where(Invite.token == token))
        ).scalar_one_or_none()
        if invite is None:
            raise APIException(404, "INVITE_NOT_FOUND", "Invite not found")
        if invite.accepted:
            raise APIException(400, "INVITE_ALREADY_USED", "This invitation has already been used")
        if invite.expires_at <= datetime.now(timezone.utc):
            raise APIException(
                400, "INVITE_EXPIRED", "This invitation has expired — ask for a new one"
            )
        # Strict: the logged-in user must own the invited phone number.
        if user.phone != invite.phone:
            raise APIException(
                403, "INVITE_PHONE_MISMATCH",
                "This invite was sent to a different phone number",
            )

        child = (
            await self.db.execute(
                select(Child).where(Child.id == invite.child_id, Child.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if child is None:
            raise APIException(404, "CHILD_NOT_FOUND", "Child not found")

        # Idempotent if somehow already a member.
        membership = (
            await self.db.execute(
                select(FamilyMember).where(
                    FamilyMember.child_id == invite.child_id, FamilyMember.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            membership = FamilyMember(
                child_id=invite.child_id,
                user_id=user.id,
                role=invite.role,
                is_primary=False,
                can_view=invite.can_view,
                can_call=invite.can_call,
                can_manage=invite.can_manage,
            )
            self.db.add(membership)

        invite.accepted = True
        await self.db.commit()
        await self.db.refresh(membership)
        # TODO(Sprint 2): FCM notify the primary parent that the guardian accepted.
        return child, membership

    # ---------------------------------------------------------------- helpers
    async def _guard_already_member(self, child_id: uuid.UUID, phone: str) -> None:
        exists = (
            await self.db.execute(
                select(FamilyMember.id)
                .join(User, User.id == FamilyMember.user_id)
                .where(FamilyMember.child_id == child_id, User.phone == phone)
            )
        ).first()
        if exists:
            raise APIException(400, "ALREADY_MEMBER", "This person is already a family member")

    async def _guard_duplicate_pending(self, child_id: uuid.UUID, phone: str) -> None:
        pending = (
            await self.db.execute(
                select(Invite.id).where(
                    Invite.child_id == child_id,
                    Invite.phone == phone,
                    Invite.accepted.is_(False),
                    Invite.expires_at > datetime.now(timezone.utc),
                )
            )
        ).first()
        if pending:
            raise APIException(
                400, "INVITE_ALREADY_SENT", "An invite is already pending for this number"
            )

    async def _enforce_guardian_limit(self, child_id: uuid.UUID) -> None:
        primary = (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .where(FamilyMember.child_id == child_id, FamilyMember.is_primary.is_(True))
            )
        ).scalars().first()
        tier = effective_tier(primary) if primary else "free"
        limit = GUARDIAN_LIMITS.get(tier)
        if limit is None:
            return

        now = datetime.now(timezone.utc)
        members = (
            await self.db.execute(
                select(func.count())
                .select_from(FamilyMember)
                .where(FamilyMember.child_id == child_id, FamilyMember.is_primary.is_(False))
            )
        ).scalar_one()
        pending = (
            await self.db.execute(
                select(func.count())
                .select_from(Invite)
                .where(
                    Invite.child_id == child_id,
                    Invite.accepted.is_(False),
                    Invite.expires_at > now,
                )
            )
        ).scalar_one()
        if members + pending >= limit:
            raise APIException(
                402, "GUARDIAN_LIMIT_REACHED",
                _UPGRADE_MSG.get(tier, "Upgrade your plan to add more guardians"),
            )
