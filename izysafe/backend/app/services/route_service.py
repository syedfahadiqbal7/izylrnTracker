"""Safe Route CRUD with the Premium tier gate (Sprint 7 Slice 1, F20).

A Safe Route is an ordered polyline (≥2 waypoints) with a deviation tolerance and a
schedule; the deviation engine (`RouteDeviationService`) alerts when a child strays
further than the tolerance while the route is active. Authorization reuses
`family_members` (CLAUDE.md §3.10) exactly like geofences: child access is delegated
to ChildrenService (manage to write, view to read; non-members get 404), and
route-by-id access is resolved through the owning child's membership.

Safe Routes are Premium-only (CLAUDE.md §10) — gated over the child's PRIMARY parent
(the paying account), consistent with the geofence/guardian limits. There is no
per-child count cap (Premium is uncapped).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.errors import APIException
from app.models.child import FamilyMember
from app.models.route import SafeRoute
from app.models.user import User
from app.services.children_service import ChildrenService, effective_tier

# Safe Routes is a Premium feature (School inherits it).
ROUTE_TIERS = {"premium", "school"}

Permission = Literal["view", "manage"]

logger = logging.getLogger("izysafe.route")


class RouteService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis
        self.children = ChildrenService(db)

    # ----------------------------------------------------------------- create
    async def create_route(
        self, user, child_id: uuid.UUID, data: dict[str, Any]
    ) -> SafeRoute:
        await self.children.get_child(user, child_id, require="manage")
        self._enforce_tier(await self._child_tier(child_id))

        route = SafeRoute(child_id=child_id, **data)
        self.db.add(route)
        await self.db.commit()
        await self.db.refresh(route)
        await self._invalidate(child_id)
        return route

    # ------------------------------------------------------------------- read
    async def list_routes(self, user, child_id: uuid.UUID) -> list[SafeRoute]:
        await self.children.get_child(user, child_id, require="view")
        rows = (
            await self.db.execute(
                select(SafeRoute)
                .where(SafeRoute.child_id == child_id)
                .order_by(SafeRoute.created_at)
            )
        ).scalars().all()
        return list(rows)

    async def get_route(
        self, user, route_id: uuid.UUID, require: Permission = "view"
    ) -> SafeRoute:
        route, _ = await self._require_route(user.id, route_id, require)
        return route

    # ----------------------------------------------------------------- update
    async def update_route(
        self, user, route_id: uuid.UUID, fields: dict[str, Any]
    ) -> SafeRoute:
        route, _ = await self._require_route(user.id, route_id, "manage")
        for key, value in fields.items():
            setattr(route, key, value)
        child_id = route.child_id
        await self.db.commit()
        await self.db.refresh(route)
        await self._invalidate(child_id)
        return route

    # ----------------------------------------------------------------- delete
    async def delete_route(self, user, route_id: uuid.UUID) -> None:
        route, _ = await self._require_route(user.id, route_id, "manage")
        child_id = route.child_id
        await self.db.delete(route)  # hard delete — routes have no soft-delete
        await self.db.commit()
        await self._invalidate(child_id)

    # ---------------------------------------------------------------- helpers
    def _enforce_tier(self, tier: str) -> None:
        if tier not in ROUTE_TIERS:
            raise APIException(
                402, "SAFE_ROUTES_REQUIRES_PREMIUM",
                "Upgrade to Premium plan to add safe routes",
            )

    async def _invalidate(self, child_id: uuid.UUID) -> None:
        """Drop the cached active-route bundle so the deviation engine reloads it.
        Redis hiccups must not fail the CRUD request."""
        try:
            await self.redis.delete(rk.active_routes(child_id))
        except Exception:
            logger.warning("Could not invalidate active-route cache for child %s", child_id)

    async def _child_tier(self, child_id: uuid.UUID) -> str:
        primary = (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .where(FamilyMember.child_id == child_id, FamilyMember.is_primary.is_(True))
            )
        ).scalars().first()
        return effective_tier(primary) if primary else "free"

    async def _require_route(
        self, user_id: uuid.UUID, route_id: uuid.UUID, need: Permission
    ) -> tuple[SafeRoute, FamilyMember]:
        row = (
            await self.db.execute(
                select(SafeRoute, FamilyMember)
                .join(FamilyMember, FamilyMember.child_id == SafeRoute.child_id)
                .where(SafeRoute.id == route_id, FamilyMember.user_id == user_id)
            )
        ).first()
        # 404 (not 403) when the user has no membership — don't reveal existence.
        if row is None:
            raise APIException(404, "SAFE_ROUTE_NOT_FOUND", "Safe route not found")
        route, membership = row
        if need == "view" and not membership.can_view:
            raise APIException(403, "FORBIDDEN", "You don't have permission to view this route")
        if need == "manage" and not membership.can_manage:
            raise APIException(403, "FORBIDDEN", "You don't have permission to manage this route")
        return route, membership
