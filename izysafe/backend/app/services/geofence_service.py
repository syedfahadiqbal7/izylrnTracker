"""Geofence CRUD with tier gating (Sprint 3 Slice 1).

Authorization reuses the family_members model (CLAUDE.md §3.10) — child access is
delegated to ChildrenService; geofence-by-id access is resolved through the owning
child's membership. Tier limits are counted over the child's PRIMARY parent (the
paying account), consistent with the children/guardian limits.

Two gates on create (and on update when the shape changes):
  * per-child zone count  — Free=1, Basic=5, Premium/School=unlimited
  * polygon zones         — Premium/School only (F19)
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.errors import APIException
from app.core.geometry import is_inside_circle, is_inside_polygon
from app.models.child import FamilyMember
from app.models.location import Geofence, GeofenceEvent
from app.models.user import User
from app.schemas.geofence import validate_shape
from app.services.children_service import ChildrenService, effective_tier
from app.services.geocoding_gateway import GeocodingGateway

# None = unlimited. Limit is PER CHILD (zones nest under a child).
GEOFENCE_LIMITS: dict[str, int | None] = {"free": 1, "basic": 5, "premium": None, "school": None}
POLYGON_TIERS = {"premium", "school"}

# Safe Addresses (F24) are geofences of any zone_type EXCEPT school (school drives
# School Mode; the rest are named safe places — schema.sql DESIGN NOTE 7).
SAFE_ADDRESS_ZONE_TYPES = ("home", "tuition", "grandparents", "sports", "other")

_LIMIT_UPGRADE_MSG = {
    "free": "Upgrade to Basic plan to add more zones",
    "basic": "Upgrade to Premium plan for unlimited zones",
}

logger = logging.getLogger("izysafe.geofence")

Permission = Literal["view", "manage"]


class GeofenceService:
    def __init__(
        self, db: AsyncSession, redis: Redis, geocoder: GeocodingGateway | None = None
    ) -> None:
        self.db = db
        self.redis = redis
        self.geocoder = geocoder
        self.children = ChildrenService(db)

    # ----------------------------------------------------------------- create
    async def create_geofence(
        self, user, child_id: uuid.UUID, data: dict[str, Any]
    ) -> Geofence:
        # Authorize: caller must be able to MANAGE this child (404 for non-members).
        await self.children.get_child(user, child_id, require="manage")

        tier = await self._child_tier(child_id)
        await self._enforce_zone_limit(child_id, tier)
        self._enforce_polygon_gate(data.get("type", "circle"), tier)

        # Auto-label a Safe Address / zone when no address was typed (F24). Best-effort:
        # reverse-geocode the circle centre; a null result leaves address unset.
        if (
            self.geocoder is not None
            and not data.get("address")
            and data.get("type", "circle") == "circle"
            and data.get("center_lat") is not None
            and data.get("center_lng") is not None
        ):
            data = dict(data)
            data["address"] = await self.geocoder.reverse_geocode(
                data["center_lat"], data["center_lng"]
            )

        geofence = Geofence(child_id=child_id, **data)
        self.db.add(geofence)
        await self.db.commit()
        await self.db.refresh(geofence)
        await self._invalidate(child_id)
        return geofence

    # ------------------------------------------------------------------- read
    async def list_geofences(self, user, child_id: uuid.UUID) -> list[Geofence]:
        await self.children.get_child(user, child_id, require="view")
        rows = (
            await self.db.execute(
                select(Geofence)
                .where(Geofence.child_id == child_id)
                .order_by(Geofence.created_at)
            )
        ).scalars().all()
        return list(rows)

    async def list_safe_addresses(self, user, child_id: uuid.UUID) -> list[Geofence]:
        """Safe Addresses (F24): the child's non-school named places — a convenience
        filtered view over the same geofences table (no separate concept/table)."""
        await self.children.get_child(user, child_id, require="view")
        rows = (
            await self.db.execute(
                select(Geofence)
                .where(
                    Geofence.child_id == child_id,
                    Geofence.zone_type.in_(SAFE_ADDRESS_ZONE_TYPES),
                )
                .order_by(Geofence.created_at)
            )
        ).scalars().all()
        return list(rows)

    async def get_geofence(
        self, user, geofence_id: uuid.UUID, require: Permission = "view"
    ) -> Geofence:
        geofence, _ = await self._require_geofence(user.id, geofence_id, require)
        return geofence

    async def list_events(
        self, user, geofence_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[GeofenceEvent], int]:
        """Enter/exit history for a zone (most recent first), with a total count."""
        await self._require_geofence(user.id, geofence_id, "view")
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(GeofenceEvent)
                .where(GeofenceEvent.geofence_id == geofence_id)
            )
        ).scalar_one()
        rows = (
            await self.db.execute(
                select(GeofenceEvent)
                .where(GeofenceEvent.geofence_id == geofence_id)
                .order_by(GeofenceEvent.timestamp.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), total

    # ----------------------------------------------------------------- update
    async def update_geofence(
        self, user, geofence_id: uuid.UUID, fields: dict[str, Any]
    ) -> Geofence:
        geofence, _ = await self._require_geofence(user.id, geofence_id, "manage")

        for key, value in fields.items():
            setattr(geofence, key, value)

        # Re-validate the resulting shape (type may have changed) + polygon gate.
        validate_shape(
            geofence.type,
            geofence.center_lat,
            geofence.center_lng,
            geofence.radius_m,
            geofence.polygon_points,
        )
        if "type" in fields:
            tier = await self._child_tier(geofence.child_id)
            self._enforce_polygon_gate(geofence.type, tier)

        child_id = geofence.child_id
        await self.db.commit()
        await self.db.refresh(geofence)
        await self._invalidate(child_id)
        return geofence

    # ----------------------------------------------------------------- delete
    async def delete_geofence(self, user, geofence_id: uuid.UUID) -> None:
        geofence, _ = await self._require_geofence(user.id, geofence_id, "manage")
        child_id = geofence.child_id
        await self.db.delete(geofence)  # hard delete — geofences have no soft-delete
        await self.db.commit()
        await self._invalidate(child_id)

    # --------------------------------------------------------------- geometry
    @staticmethod
    def is_point_inside(geofence: Geofence, lat: float, lng: float) -> bool:
        """Whether (lat, lng) falls inside a zone — dispatches on geofence.type.

        Slice 2 building block (Decision A: pure-Python Haversine + ray-casting).
        Slice 3's check_all_fences() will call this to drive enter/exit transitions
        (Redis state + 5-min debounce + FCM fan-out). No DB/I/O here so it stays
        cheap on the webhook BackgroundTask path.
        """
        if geofence.type == "polygon":
            return is_inside_polygon(lat, lng, geofence.polygon_points or [])
        return is_inside_circle(
            lat, lng, geofence.center_lat, geofence.center_lng, geofence.radius_m
        )

    # ---------------------------------------------------------------- helpers
    async def _invalidate(self, child_id: uuid.UUID) -> None:
        """Drop the cached active-fence bundle so the breach engine reloads it
        (Decision E). Redis hiccups must not fail the CRUD request."""
        try:
            await self.redis.delete(rk.active_fences(child_id))
        except Exception:
            logger.warning("Could not invalidate active-fence cache for child %s", child_id)

    async def _child_tier(self, child_id: uuid.UUID) -> str:
        """Effective tier of the child's primary parent (the paying account)."""
        primary = (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .where(
                    FamilyMember.child_id == child_id,
                    FamilyMember.is_primary.is_(True),
                )
            )
        ).scalars().first()
        return effective_tier(primary) if primary else "free"

    async def _enforce_zone_limit(self, child_id: uuid.UUID, tier: str) -> None:
        limit = GEOFENCE_LIMITS.get(tier)
        if limit is None:
            return
        count = (
            await self.db.execute(
                select(func.count())
                .select_from(Geofence)
                .where(Geofence.child_id == child_id)
            )
        ).scalar_one()
        if count >= limit:
            raise APIException(
                402, "GEOFENCE_LIMIT_REACHED",
                _LIMIT_UPGRADE_MSG.get(tier, "Upgrade your plan to add more zones"),
            )

    def _enforce_polygon_gate(self, gtype: str, tier: str) -> None:
        if gtype == "polygon" and tier not in POLYGON_TIERS:
            raise APIException(
                402, "POLYGON_REQUIRES_PREMIUM",
                "Upgrade to Premium plan to draw custom polygon zones",
            )

    async def _require_geofence(
        self, user_id: uuid.UUID, geofence_id: uuid.UUID, need: Permission
    ) -> tuple[Geofence, FamilyMember]:
        row = (
            await self.db.execute(
                select(Geofence, FamilyMember)
                .join(FamilyMember, FamilyMember.child_id == Geofence.child_id)
                .where(Geofence.id == geofence_id, FamilyMember.user_id == user_id)
            )
        ).first()
        # 404 (not 403) when the user has no membership — don't reveal existence.
        if row is None:
            raise APIException(404, "GEOFENCE_NOT_FOUND", "Geofence not found")

        geofence, membership = row
        if need == "view" and not membership.can_view:
            raise APIException(403, "FORBIDDEN", "You don't have permission to view this zone")
        if need == "manage" and not membership.can_manage:
            raise APIException(403, "FORBIDDEN", "You don't have permission to manage this zone")
        return geofence, membership
