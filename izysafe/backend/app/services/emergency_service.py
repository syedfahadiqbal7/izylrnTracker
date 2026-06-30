"""Emergency Contacts CRUD (Sprint 4 Slice 3).

Premium-gated (CLAUDE.md §10) — counted over the child's primary parent, like the
geofence/guardian limits. Authorization reuses `family_members` (manage to write,
view to read; non-members get 404). `is_app_user` is derived server-side by matching
the contact's phone to a registered user, so the SOS fan-out can reach them by FCM.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIException
from app.core.validators import validate_phone
from app.models.child import FamilyMember
from app.models.sos import EmergencyContact
from app.models.user import User
from app.services.children_service import ChildrenService, effective_tier

# Emergency Contacts is a Premium feature (School inherits it).
EMERGENCY_TIERS = {"premium", "school"}

Permission = Literal["view", "manage"]


class EmergencyContactService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.children = ChildrenService(db)

    # ----------------------------------------------------------------- create
    async def create(self, user, child_id: uuid.UUID, data: dict[str, Any]) -> EmergencyContact:
        await self.children.get_child(user, child_id, require="manage")
        self._enforce_tier(await self._child_tier(child_id))

        data = dict(data)
        data["phone"] = validate_phone(data["phone"])
        contact = EmergencyContact(
            child_id=child_id, is_app_user=await self._is_app_user(data["phone"]), **data
        )
        self.db.add(contact)
        await self.db.commit()
        await self.db.refresh(contact)
        return contact

    # ------------------------------------------------------------------- read
    async def list(self, user, child_id: uuid.UUID) -> list[EmergencyContact]:
        await self.children.get_child(user, child_id, require="view")
        rows = (
            await self.db.execute(
                select(EmergencyContact)
                .where(EmergencyContact.child_id == child_id)
                .order_by(EmergencyContact.created_at)
            )
        ).scalars().all()
        return list(rows)

    # ----------------------------------------------------------------- update
    async def update(
        self, user, contact_id: uuid.UUID, fields: dict[str, Any]
    ) -> EmergencyContact:
        contact, _ = await self._require_contact(user.id, contact_id, "manage")
        fields = dict(fields)
        if "phone" in fields and fields["phone"] is not None:
            fields["phone"] = validate_phone(fields["phone"])
            fields["is_app_user"] = await self._is_app_user(fields["phone"])
        for key, value in fields.items():
            setattr(contact, key, value)
        await self.db.commit()
        await self.db.refresh(contact)
        return contact

    # ----------------------------------------------------------------- delete
    async def delete(self, user, contact_id: uuid.UUID) -> None:
        contact, _ = await self._require_contact(user.id, contact_id, "manage")
        await self.db.delete(contact)
        await self.db.commit()

    # ---------------------------------------------------------------- helpers
    def _enforce_tier(self, tier: str) -> None:
        if tier not in EMERGENCY_TIERS:
            raise APIException(
                402, "EMERGENCY_CONTACTS_REQUIRES_PREMIUM",
                "Upgrade to Premium plan to add emergency contacts",
            )

    async def _child_tier(self, child_id: uuid.UUID) -> str:
        primary = (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .where(FamilyMember.child_id == child_id, FamilyMember.is_primary.is_(True))
            )
        ).scalars().first()
        return effective_tier(primary) if primary else "free"

    async def _is_app_user(self, phone: str) -> bool:
        row = (
            await self.db.execute(
                select(User.id).where(User.phone == phone, User.deleted_at.is_(None))
            )
        ).first()
        return row is not None

    async def _require_contact(
        self, user_id: uuid.UUID, contact_id: uuid.UUID, need: Permission
    ) -> tuple[EmergencyContact, FamilyMember]:
        row = (
            await self.db.execute(
                select(EmergencyContact, FamilyMember)
                .join(FamilyMember, FamilyMember.child_id == EmergencyContact.child_id)
                .where(EmergencyContact.id == contact_id, FamilyMember.user_id == user_id)
            )
        ).first()
        if row is None:
            raise APIException(404, "EMERGENCY_CONTACT_NOT_FOUND", "Emergency contact not found")
        contact, membership = row
        if need == "view" and not membership.can_view:
            raise APIException(403, "FORBIDDEN", "You don't have permission to view this contact")
        if need == "manage" and not membership.can_manage:
            raise APIException(403, "FORBIDDEN", "You don't have permission to manage this contact")
        return contact, membership
