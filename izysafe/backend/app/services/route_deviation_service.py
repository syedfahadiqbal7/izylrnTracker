"""Safe Route deviation detection (Sprint 7 Slice 1, F20) — a Flow-B sibling.

Runs in a webhook BackgroundTask (never the hot path, §4). For each position it
measures the child's distance to every *active* Safe Route (min point-to-polyline
distance, pure Python) and detects on-route → off-route transitions against a
per-route Redis state — subject to the route's schedule and a 5-minute anti-jitter
debounce — fanning a `route_deviation` alert out to the family via `AlertService`.

Design mirrors `GeofenceBreachService` deliberately:
  * The active-route set + the child's name + the primary parent's timezone/tier are
    cached per child in Redis (`active_routes:{child}`, invalidated by CRUD). The
    common on-route ping then touches Redis only — no DB read.
  * Per route state `route:{child}:{route}:deviating` ('true'/'false'/None) is ALWAYS
    rewritten to the current side (72h TTL), so a suppressed transition can't re-fire.
    A None baseline never alerts (we don't know the prior side).
  * Only the on-route → off-route edge alerts (returning to the route re-arms
    silently). Firing additionally requires the route's schedule window (active_days +
    active_from/to in the primary parent's tz) and no debounce marker; a real fire
    sets `route_debounce:{child}:{route}` for 5 minutes.

Safe Routes is Premium (CLAUDE.md §10): if the primary parent's effective tier isn't
Premium+ (e.g. after a lapse/downgrade), detection is skipped even when routes exist.
There is no route-event ledger table — the alert inbox row is the record.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.geometry import distance_to_route_m
from app.models.child import Child, FamilyMember
from app.models.route import SafeRoute
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.children_service import effective_tier
from app.services.fcm_gateway import FcmGateway

logger = logging.getLogger("izysafe.route")

# Safe Routes is a Premium feature (School inherits it).
ROUTE_TIERS = {"premium", "school"}


class RouteDeviationService:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        redis: Redis,
        fcm: FcmGateway,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.fcm = fcm

    # ------------------------------------------------------------------ public
    async def check_all_routes(
        self,
        child_id: uuid.UUID,
        lat: float,
        lng: float,
        device_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        bundle = await self._get_bundle(child_id)
        if bundle["tier"] not in ROUTE_TIERS:
            return  # Premium-gated feature — inert on free/lapsed tiers
        routes = bundle["routes"]
        if not routes:
            return

        # (route, distance_m) tuples that pass every gate.
        to_fire: list[tuple[dict, float]] = []
        for route in routes:
            try:
                distance = distance_to_route_m(lat, lng, route["waypoints"])
            except Exception:  # a malformed route must not stop the others
                logger.exception("Route eval failed for route %s", route.get("id"))
                continue
            deviating = distance > route["deviation_tolerance_m"]

            state_key = rk.route_deviating(child_id, route["id"])
            prev = await self.redis.get(state_key)
            await self.redis.set(
                state_key, "true" if deviating else "false", ex=rk.ROUTE_STATE_TTL
            )

            if prev is None or (prev == "true") == deviating:
                continue  # baseline or no change
            if not deviating:
                continue  # returned to the route — re-arm silently, no alert
            if not self._within_schedule(route, bundle["tz"], now):
                continue
            if await self.redis.get(rk.route_debounce(child_id, route["id"])):
                continue  # jitter debounce

            to_fire.append((route, distance))

        if to_fire:
            await self._fire(child_id, lat, lng, bundle["child_name"], to_fire)

    # --------------------------------------------------------------- internals
    @staticmethod
    def _within_schedule(route: dict, tz_name: str, now: datetime) -> bool:
        """Honor the route's active_days + active_from/active_to (primary parent tz).
        Overnight ranges (from > to) are supported; from == to never matches."""
        days = route.get("active_days") or []
        from_iso, to_iso = route.get("active_from"), route.get("active_to")
        try:
            local = now.astimezone(ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, ValueError):
            local = now.astimezone(timezone.utc)
        if days and local.isoweekday() not in days:
            return False
        if from_iso and to_iso:
            t = local.time()
            f, u = time.fromisoformat(from_iso), time.fromisoformat(to_iso)
            return f <= t <= u if f <= u else (t >= f or t <= u)
        return True

    async def _fire(
        self,
        child_id: uuid.UUID,
        lat: float,
        lng: float,
        child_name: str,
        to_fire: list[tuple[dict, float]],
    ) -> None:
        async with self.session_factory() as session:
            alerts = AlertService(session, self.fcm)
            for route, distance in to_fire:
                await alerts.notify_family(
                    child_id,
                    "route_deviation",
                    f"Off safe route: {route['name']}",
                    f"{child_name} has strayed from {route['name']}.",
                    {
                        "route_id": route["id"],
                        "route_name": route["name"],
                        "lat": lat,
                        "lng": lng,
                        "distance_m": round(distance),
                    },
                )
            await session.commit()

        # Debounce only after a real fire (mirrors geofence/speed ordering).
        for route, _ in to_fire:
            await self.redis.set(
                rk.route_debounce(child_id, route["id"]),
                "1",
                ex=settings.route_debounce_seconds,
            )
            logger.info("Route deviation %s for child %s", route["id"], child_id)

    async def _get_bundle(self, child_id: uuid.UUID) -> dict:
        """Active-route bundle for a child, Redis-cached (mirrors active_fences)."""
        cached = await self.redis.get(rk.active_routes(child_id))
        if cached is not None:
            return json.loads(cached)

        async with self.session_factory() as session:
            bundle = await self._load_bundle(session, child_id)
        await self.redis.set(
            rk.active_routes(child_id), json.dumps(bundle), ex=rk.ACTIVE_ROUTES_TTL
        )
        return bundle

    async def _load_bundle(self, session: AsyncSession, child_id: uuid.UUID) -> dict:
        routes = (
            await session.execute(
                select(SafeRoute).where(
                    SafeRoute.child_id == child_id, SafeRoute.active.is_(True)
                )
            )
        ).scalars().all()
        meta = (
            await session.execute(
                select(Child, User)
                .join(FamilyMember, FamilyMember.child_id == Child.id)
                .join(User, User.id == FamilyMember.user_id)
                .where(
                    Child.id == child_id,
                    FamilyMember.is_primary.is_(True),
                    Child.deleted_at.is_(None),
                )
            )
        ).first()

        if meta is None:
            return {
                "tz": "UTC", "child_name": "Your child", "tier": "free",
                "routes": [self._route_dict(r) for r in routes],
            }
        child, parent = meta
        return {
            "tz": parent.timezone,
            "child_name": child.name,
            "tier": effective_tier(parent),
            "routes": [self._route_dict(r) for r in routes],
        }

    @staticmethod
    def _route_dict(r: SafeRoute) -> dict:
        return {
            "id": str(r.id),
            "name": r.name,
            "waypoints": r.waypoints,
            "deviation_tolerance_m": r.deviation_tolerance_m,
            "active_days": r.active_days,
            "active_from": r.active_from.isoformat() if r.active_from else None,
            "active_to": r.active_to.isoformat() if r.active_to else None,
        }
