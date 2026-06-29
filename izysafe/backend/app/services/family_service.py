"""Family member management: list, update permissions, remove, manage invites.

Rules:
  * Listing requires can_view; updating others / listing-or-revoking invites
    requires can_manage.
  * The primary parent is protected: cannot be removed or downgraded.
  * is_primary is not editable here (no primary transfer in v1).
  * Self-removal is allowed for any member (a guardian may leave); removing
    another member requires can_manage. The primary parent cannot self-remove.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIException
from app.models.child import FamilyMember, Invite
from app.models.user import User
from app.services.children_service import ChildrenService


class FamilyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.children = ChildrenService(db)

    # ------------------------------------------------------------------- list
    async def list_members(self, user, child_id: uuid.UUID) -> list[tuple[FamilyMember, User]]:
        await self.children.get_child(user, child_id, require="view")
        rows = (
            await self.db.execute(
                select(FamilyMember, User)
                .join(User, User.id == FamilyMember.user_id)
                .where(FamilyMember.child_id == child_id)
                .order_by(FamilyMember.is_primary.desc(), FamilyMember.created_at)
            )
        ).all()
        return [(fm, u) for fm, u in rows]

    # ----------------------------------------------------------------- update
    async def update_member(
        self, user, child_id: uuid.UUID, member_id: uuid.UUID, fields: dict[str, Any]
    ) -> tuple[FamilyMember, User]:
        await self.children.get_child(user, child_id, require="manage")
        target = await self._target_member(child_id, member_id)
        if target.is_primary:
            raise APIException(403, "PRIMARY_PROTECTED", "The primary parent cannot be modified")

        for key, value in fields.items():
            setattr(target, key, value)
        await self.db.commit()
        await self.db.refresh(target)
        member_user = await self.db.get(User, target.user_id)
        return target, member_user

    # ----------------------------------------------------------------- remove
    async def remove_member(self, user, child_id: uuid.UUID, member_id: uuid.UUID) -> None:
        requester = await self._membership(child_id, user.id)
        if requester is None:
            raise APIException(404, "CHILD_NOT_FOUND", "Child not found")

        target = await self._target_member(child_id, member_id)
        if target.is_primary:
            raise APIException(403, "PRIMARY_PROTECTED", "The primary parent cannot be removed")

        is_self = target.user_id == user.id
        if not is_self and not requester.can_manage:
            raise APIException(403, "FORBIDDEN", "You don't have permission to remove members")

        await self.db.delete(target)
        await self.db.commit()

    # ---------------------------------------------------------------- invites
    async def list_invites(self, user, child_id: uuid.UUID) -> list[Invite]:
        await self.children.get_child(user, child_id, require="manage")
        rows = (
            await self.db.execute(
                select(Invite)
                .where(Invite.child_id == child_id, Invite.accepted.is_(False))
                .order_by(Invite.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def revoke_invite(self, user, token: str) -> None:
        invite = (
            await self.db.execute(select(Invite).where(Invite.token == token))
        ).scalar_one_or_none()
        if invite is None:
            raise APIException(404, "INVITE_NOT_FOUND", "Invite not found")
        if invite.accepted:
            raise APIException(
                400, "INVITE_ALREADY_USED",
                "This invite was already accepted — remove the member instead",
            )
        # Caller must be able to manage the child this invite belongs to.
        await self.children.get_child(user, invite.child_id, require="manage")
        await self.db.delete(invite)
        await self.db.commit()

    # ---------------------------------------------------------------- helpers
    async def _membership(self, child_id: uuid.UUID, user_id: uuid.UUID) -> FamilyMember | None:
        return (
            await self.db.execute(
                select(FamilyMember).where(
                    FamilyMember.child_id == child_id, FamilyMember.user_id == user_id
                )
            )
        ).scalar_one_or_none()

    async def _target_member(self, child_id: uuid.UUID, member_id: uuid.UUID) -> FamilyMember:
        target = await self.db.get(FamilyMember, member_id)
        if target is None or target.child_id != child_id:
            raise APIException(404, "MEMBER_NOT_FOUND", "Family member not found")
        return target

    @staticmethod
    def is_expired(invite: Invite) -> bool:
        return invite.expires_at <= datetime.now(timezone.utc)
