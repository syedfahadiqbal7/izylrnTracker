"""Children CRUD with the ownership model, tier limits, and soft deletes.

Ownership (CLAUDE.md §3.10): a child has no owner FK. The creator is recorded in
family_members as role='parent', is_primary=True, can_manage=True. The tier
"max children" limit is counted over children where the user is the PRIMARY parent.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIException
from app.models.child import Child, FamilyMember
from app.models.device import Device

# None = unlimited. Premium + School are uncapped here (School is custom/contractual).
CHILD_LIMITS: dict[str, int | None] = {"free": 1, "basic": 3, "premium": None, "school": None}

_UPGRADE_MSG = {
    "free": "Upgrade to Basic plan to add more children",
    "basic": "Upgrade to Premium plan for unlimited children",
}

Permission = Literal["view", "manage", "primary"]


class ChildrenService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----------------------------------------------------------------- create
    async def create_child(self, user, data: dict[str, Any]) -> tuple[Child, FamilyMember]:
        await self._enforce_tier_limit(user)

        child = Child(**data)
        self.db.add(child)
        await self.db.flush()  # need child.id for the membership row

        membership = FamilyMember(
            child_id=child.id,
            user_id=user.id,
            role="parent",
            is_primary=True,
            can_view=True,
            can_call=True,
            can_manage=True,
        )
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(child)
        return child, membership

    # ------------------------------------------------------------------- read
    async def list_children(self, user) -> list[tuple[Child, FamilyMember, int]]:
        rows = (
            await self.db.execute(
                select(Child, FamilyMember)
                .join(FamilyMember, FamilyMember.child_id == Child.id)
                .where(FamilyMember.user_id == user.id, Child.deleted_at.is_(None))
                .order_by(Child.created_at)
            )
        ).all()

        counts = await self._device_counts([c.id for c, _ in rows])
        return [(c, fm, counts.get(c.id, 0)) for c, fm in rows]

    async def get_child(
        self, user, child_id: uuid.UUID, require: Permission = "view"
    ) -> tuple[Child, FamilyMember, int]:
        child, membership = await self._require_membership(user.id, child_id, require)
        counts = await self._device_counts([child.id])
        return child, membership, counts.get(child.id, 0)

    # ----------------------------------------------------------------- update
    async def update_child(self, user, child_id: uuid.UUID, fields: dict[str, Any]) -> tuple[Child, FamilyMember]:
        child, membership = await self._require_membership(user.id, child_id, "manage")
        for key, value in fields.items():
            setattr(child, key, value)
        await self.db.commit()
        await self.db.refresh(child)
        return child, membership

    # ----------------------------------------------------------------- delete
    async def soft_delete_child(self, user, child_id: uuid.UUID) -> None:
        # Only the primary parent may delete a child.
        child, _ = await self._require_membership(user.id, child_id, "primary")
        child.deleted_at = datetime.now(timezone.utc)
        child.active = False
        await self.db.commit()

    # ---------------------------------------------------------------- helpers
    def _effective_tier(self, user) -> str:
        tier = user.subscription_tier
        if tier != "free" and user.subscription_expires_at:
            if user.subscription_expires_at < datetime.now(timezone.utc):
                return "free"
        return tier

    async def _enforce_tier_limit(self, user) -> None:
        tier = self._effective_tier(user)
        limit = CHILD_LIMITS.get(tier)
        if limit is None:
            return
        count = (
            await self.db.execute(
                select(func.count())
                .select_from(FamilyMember)
                .join(Child, Child.id == FamilyMember.child_id)
                .where(
                    FamilyMember.user_id == user.id,
                    FamilyMember.is_primary.is_(True),
                    Child.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        if count >= limit:
            raise APIException(
                402, "CHILD_LIMIT_REACHED",
                _UPGRADE_MSG.get(tier, "Upgrade your plan to add more children"),
            )

    async def _require_membership(
        self, user_id: uuid.UUID, child_id: uuid.UUID, need: Permission
    ) -> tuple[Child, FamilyMember]:
        row = (
            await self.db.execute(
                select(Child, FamilyMember)
                .join(FamilyMember, FamilyMember.child_id == Child.id)
                .where(
                    Child.id == child_id,
                    Child.deleted_at.is_(None),
                    FamilyMember.user_id == user_id,
                )
            )
        ).first()
        # 404 (not 403) when the user has no membership — don't reveal the child exists.
        if row is None:
            raise APIException(404, "CHILD_NOT_FOUND", "Child not found")

        child, membership = row
        if need == "view" and not membership.can_view:
            raise APIException(403, "FORBIDDEN", "You don't have permission to view this child")
        if need == "manage" and not membership.can_manage:
            raise APIException(403, "FORBIDDEN", "You don't have permission to manage this child")
        if need == "primary" and not membership.is_primary:
            raise APIException(403, "FORBIDDEN", "Only the primary parent can perform this action")
        return child, membership

    async def _device_counts(self, child_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not child_ids:
            return {}
        rows = (
            await self.db.execute(
                select(Device.child_id, func.count())
                .where(
                    Device.child_id.in_(child_ids),
                    Device.deleted_at.is_(None),
                    Device.active.is_(True),
                )
                .group_by(Device.child_id)
            )
        ).all()
        return {cid: n for cid, n in rows}
