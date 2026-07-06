"""Device pairing & management for parents (Sprint 11).

The missing link that makes Flow A usable end-to-end: a parent pairs a child's GPS
tracker here, which (1) creates the local `devices` row and (2) registers the tracker
in Traccar so its incoming fixes resolve to this child (LocationService matches on
`traccar_id`, IMEI as fallback). Everything downstream — live map, geofence, SOS,
battery, audio — already keys off a `Device` with a `traccar_id`; nothing here changes
those paths, it only brings the device *into* the system.

Conventions mirror the rest of the codebase:
  * Authorization flows through `family_members` — non-members get 404 (never reveal the
    child), members without `can_manage` get 403 (CLAUDE.md §Authorization).
  * The per-child device limit is a tier gate counted over the child's **primary parent**
    (like child/geofence/audio limits), returning 402 when reached.
  * Traccar registration is a **graceful seam**: an unconfigured/failed Traccar yields a
    null `traccar_id`, and pairing still succeeds locally.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.errors import APIException
from app.models.child import Child, FamilyMember
from app.models.device import Device
from app.models.user import User
from app.services.children_service import effective_tier
from app.services.traccar_gateway import TraccarGateway

# Devices per child, per tier (mirrors CLAUDE.md §10 / plans.py devices_per_child).
# None = unlimited. Counted over the child's primary parent.
DEVICE_LIMITS: dict[str, int | None] = {"free": 1, "basic": 2, "premium": 3, "school": 2}

_UPGRADE_MSG = {
    "free": "Upgrade to Basic plan to add another device for this child",
    "basic": "Upgrade to Premium plan to add another device for this child",
    "school": "This child has reached the device limit for your plan",
}


class DeviceService:
    def __init__(self, db: AsyncSession, redis: Redis, traccar: TraccarGateway) -> None:
        self.db = db
        self.redis = redis
        self.traccar = traccar

    # ----------------------------------------------------------------- create
    async def add_device(
        self, user: User, child_id: uuid.UUID, data: dict[str, Any]
    ) -> tuple[Device, bool]:
        """Pair a tracker to a child. Requires manage permission + tier headroom. Registers
        the tracker in Traccar (graceful: null traccar_id if unconfigured/failed). Returns
        the persisted device and whether it currently reports online."""
        await self._require_membership(user.id, child_id, "manage")
        await self._ensure_imei_free(data["imei"])
        await self._enforce_device_limit(child_id)

        # Register in Traccar so incoming fixes resolve to us; None on unconfigured/failure.
        traccar_id = await self.traccar.create_device(data["imei"], data["name"])

        device = Device(child_id=child_id, traccar_id=traccar_id, **data)
        self.db.add(device)
        await self.db.commit()
        await self.db.refresh(device)
        return device, await self._is_online(device)

    # ------------------------------------------------------------------- read
    async def list_devices(
        self, user: User, child_id: uuid.UUID
    ) -> list[tuple[Device, bool]]:
        await self._require_membership(user.id, child_id, "view")
        rows = (
            await self.db.execute(
                select(Device)
                .where(
                    Device.child_id == child_id,
                    Device.deleted_at.is_(None),
                )
                .order_by(Device.created_at)
            )
        ).scalars().all()
        return [(d, await self._is_online(d)) for d in rows]

    async def get_device(self, user: User, device_id: uuid.UUID) -> tuple[Device, bool]:
        device = await self._require_device(user.id, device_id, "view")
        return device, await self._is_online(device)

    # ----------------------------------------------------------------- update
    async def update_device(
        self, user: User, device_id: uuid.UUID, fields: dict[str, Any]
    ) -> tuple[Device, bool]:
        device = await self._require_device(user.id, device_id, "manage")
        for key, value in fields.items():
            setattr(device, key, value)
        await self.db.commit()
        await self.db.refresh(device)
        return device, await self._is_online(device)

    # ----------------------------------------------------------------- delete
    async def delete_device(self, user: User, device_id: uuid.UUID) -> None:
        """Unpair a device: soft-delete locally + remove it from Traccar (best-effort)."""
        device = await self._require_device(user.id, device_id, "manage")
        if device.traccar_id is not None:
            await self.traccar.delete_device(device.traccar_id)
        device.deleted_at = datetime.now(timezone.utc)
        device.active = False
        await self.db.commit()

    # ---------------------------------------------------------------- helpers
    async def _is_online(self, device: Device) -> bool:
        """Live online state: the Redis marker is source of truth (the DB column only
        aids cold loads). Falls back to the cached column if Redis is unavailable."""
        try:
            return bool(await self.redis.get(rk.device_online(device.id)))
        except Exception:  # pragma: no cover - a Redis blip shouldn't fail a read
            return device.is_online

    async def _ensure_imei_free(self, imei: str) -> None:
        # IMEI is globally UNIQUE (incl. soft-deleted rows), matching bus registration.
        taken = (
            await self.db.execute(select(Device.id).where(Device.imei == imei))
        ).first()
        if taken is not None:
            raise APIException(409, "IMEI_TAKEN", "A device with this IMEI already exists")

    async def _enforce_device_limit(self, child_id: uuid.UUID) -> None:
        primary = await self._primary_parent(child_id)
        tier = effective_tier(primary) if primary else "free"
        limit = DEVICE_LIMITS.get(tier)
        if limit is None:
            return
        count = (
            await self.db.execute(
                select(func.count())
                .select_from(Device)
                .where(
                    Device.child_id == child_id,
                    Device.deleted_at.is_(None),
                    Device.active.is_(True),
                )
            )
        ).scalar_one()
        if count >= limit:
            raise APIException(
                402, "DEVICE_LIMIT_REACHED",
                _UPGRADE_MSG.get(tier, "Upgrade your plan to add more devices"),
            )

    async def _primary_parent(self, child_id: uuid.UUID) -> User | None:
        return (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .where(FamilyMember.child_id == child_id, FamilyMember.is_primary.is_(True))
            )
        ).scalars().first()

    async def _require_membership(
        self, user_id: uuid.UUID, child_id: uuid.UUID, need: str
    ) -> FamilyMember:
        """Caller must be a member of the (non-deleted) child; 404 if not a member,
        403 if a member lacking the needed permission."""
        row = (
            await self.db.execute(
                select(FamilyMember)
                .join(Child, Child.id == FamilyMember.child_id)
                .where(
                    FamilyMember.child_id == child_id,
                    FamilyMember.user_id == user_id,
                    Child.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise APIException(404, "CHILD_NOT_FOUND", "Child not found")
        if need == "view" and not row.can_view:
            raise APIException(403, "FORBIDDEN", "You don't have permission to view this child")
        if need == "manage" and not row.can_manage:
            raise APIException(403, "FORBIDDEN", "You don't have permission to manage this child")
        return row

    async def _require_device(
        self, user_id: uuid.UUID, device_id: uuid.UUID, need: str
    ) -> Device:
        """Load a device the caller can access via family membership on its child."""
        device = (
            await self.db.execute(
                select(Device).where(
                    Device.id == device_id, Device.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        # 404 (not 403) when missing or not the caller's child — don't reveal existence.
        if device is None or device.child_id is None:
            raise APIException(404, "DEVICE_NOT_FOUND", "Device not found")
        await self._require_membership(user_id, device.child_id, need)
        return device
