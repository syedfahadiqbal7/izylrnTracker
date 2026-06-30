"""Geofence breach detection — the heart of Flow B (CLAUDE.md §5).

Runs in a webhook BackgroundTask (never the hot path, §4). For each position it
classifies the child against every *active* fence, detects enter/exit transitions
against the per-fence Redis state, and — subject to the fence's notify flags, its
schedule, and a 5-minute anti-jitter debounce — records a `geofence_events` row and
fans an alert out to the family via `AlertService`.

Performance (Decision E): the active-fence set + the child's name + the primary
parent's timezone are cached per child in Redis (`active_fences:{child}`,
invalidated by CRUD). The common no-transition ping then touches Redis only — no DB
read. A DB session is opened only on a cache miss or when a transition actually fires.

State machine, per fence:
  prev ← geofence:{child}:{fence}:inside   ('true'/'false'/None)
  cur  ← point-in-zone (haversine / ray-casting)
  state is ALWAYS rewritten to `cur` (72h TTL), so suppressed transitions still
  advance — they won't re-fire later.
  prev is None  → baseline, no alert (we don't know the prior side).
  prev == cur   → no change.
  prev != cur   → transition (enter when cur, else exit). Fire iff:
      • the matching notify flag is on (notify_enter / notify_exit), AND
      • "now" falls inside the fence schedule (active_days + active_from/to,
        evaluated in the primary parent's timezone — Decision C), AND
      • no debounce marker is set for this child+fence.
  On a real fire we set geofence_debounce:{child}:{fence} (5 min).
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
from app.core.geometry import is_inside_circle, is_inside_polygon
from app.models.child import Child, FamilyMember
from app.models.location import Geofence, GeofenceEvent
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.fcm_gateway import FcmGateway

logger = logging.getLogger("izysafe.geofence")


class GeofenceBreachService:
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
    async def check_all_fences(
        self,
        child_id: uuid.UUID,
        lat: float,
        lng: float,
        device_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        bundle = await self._get_bundle(child_id)
        fences = bundle["fences"]
        if not fences:
            return

        # (fence, direction) pairs that pass every gate and should fire.
        to_fire: list[tuple[dict, str]] = []
        for fence in fences:
            try:
                inside = self._inside(fence, lat, lng)
            except Exception:  # malformed fence must not stop the others
                logger.exception("Geofence eval failed for fence %s", fence.get("id"))
                continue

            state_key = rk.geofence_inside(child_id, fence["id"])
            prev = await self.redis.get(state_key)
            await self.redis.set(
                state_key, "true" if inside else "false", ex=rk.GEOFENCE_STATE_TTL
            )

            if prev is None or (prev == "true") == inside:
                continue  # baseline or no change

            direction = "enter" if inside else "exit"
            if direction == "enter" and not fence["notify_enter"]:
                continue
            if direction == "exit" and not fence["notify_exit"]:
                continue
            if not self._within_schedule(fence, bundle["tz"], now):
                continue
            if await self.redis.get(rk.geofence_debounce(child_id, fence["id"])):
                continue  # jitter debounce
            to_fire.append((fence, direction))

        if to_fire:
            await self._fire(child_id, device_id, lat, lng, bundle["child_name"], to_fire)

    # --------------------------------------------------------------- internals
    @staticmethod
    def _inside(fence: dict, lat: float, lng: float) -> bool:
        if fence["type"] == "polygon":
            return is_inside_polygon(lat, lng, fence["polygon_points"] or [])
        return is_inside_circle(
            lat, lng, fence["center_lat"], fence["center_lng"], fence["radius_m"]
        )

    @staticmethod
    def _within_schedule(fence: dict, tz_name: str, now: datetime) -> bool:
        """Honor active_days + active_from/active_to in the parent's timezone.

        A fence with no time window still honors active_days (the locked schema
        default is Mon–Fri). Overnight windows (from > to) are supported.
        """
        days = fence.get("active_days") or []
        af = fence.get("active_from")
        at = fence.get("active_to")
        if not days and not af:
            return True
        try:
            local = now.astimezone(ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, ValueError):
            local = now.astimezone(timezone.utc)

        if days and local.isoweekday() not in days:
            return False
        if af and at:
            t = local.time()
            af_t, at_t = time.fromisoformat(af), time.fromisoformat(at)
            in_window = af_t <= t <= at_t if af_t <= at_t else (t >= af_t or t <= at_t)
            if not in_window:
                return False
        return True

    async def _fire(
        self,
        child_id: uuid.UUID,
        device_id: uuid.UUID | None,
        lat: float,
        lng: float,
        child_name: str,
        to_fire: list[tuple[dict, str]],
    ) -> None:
        async with self.session_factory() as session:
            alerts = AlertService(session, self.fcm)
            for fence, direction in to_fire:
                fence_id = uuid.UUID(fence["id"])
                session.add(
                    GeofenceEvent(
                        child_id=child_id,
                        device_id=device_id,
                        geofence_id=fence_id,
                        event_type=direction,
                        lat=lat,
                        lng=lng,
                    )
                )
                entered = direction == "enter"
                await alerts.notify_family(
                    child_id,
                    "geofence_enter" if entered else "geofence_exit",
                    f"{'Entered' if entered else 'Left'} {fence['name']}",
                    f"{child_name} {'entered' if entered else 'left'} {fence['name']}.",
                    {
                        "geofence_id": fence["id"],
                        "zone_type": fence["zone_type"],
                        "lat": lat,
                        "lng": lng,
                    },
                )
            await session.commit()

        # Debounce only after a real fire (mirrors speed/battery ordering).
        for fence, _ in to_fire:
            await self.redis.set(
                rk.geofence_debounce(child_id, fence["id"]),
                "1",
                ex=settings.geofence_debounce_seconds,
            )
            logger.info("Geofence %s for child %s (%s)", fence["id"], child_id, _)

    async def _get_bundle(self, child_id: uuid.UUID) -> dict:
        """Active-fence bundle for a child, Redis-cached (Decision E)."""
        cached = await self.redis.get(rk.active_fences(child_id))
        if cached is not None:
            return json.loads(cached)

        async with self.session_factory() as session:
            bundle = await self._load_bundle(session, child_id)
        await self.redis.set(
            rk.active_fences(child_id), json.dumps(bundle), ex=rk.ACTIVE_FENCES_TTL
        )
        return bundle

    async def _load_bundle(self, session: AsyncSession, child_id: uuid.UUID) -> dict:
        fences = (
            await session.execute(
                select(Geofence).where(
                    Geofence.child_id == child_id, Geofence.active.is_(True)
                )
            )
        ).scalars().all()
        meta = (
            await session.execute(
                select(Child.name, User.timezone)
                .join(FamilyMember, FamilyMember.child_id == Child.id)
                .join(User, User.id == FamilyMember.user_id)
                .where(
                    Child.id == child_id,
                    FamilyMember.is_primary.is_(True),
                    Child.deleted_at.is_(None),
                )
            )
        ).first()
        child_name = meta[0] if meta else "Your child"
        tz = meta[1] if meta else "UTC"
        return {
            "tz": tz,
            "child_name": child_name,
            "fences": [self._fence_dict(f) for f in fences],
        }

    @staticmethod
    def _fence_dict(f: Geofence) -> dict:
        return {
            "id": str(f.id),
            "name": f.name,
            "zone_type": f.zone_type,
            "type": f.type,
            "center_lat": f.center_lat,
            "center_lng": f.center_lng,
            "radius_m": f.radius_m,
            "polygon_points": f.polygon_points,
            "notify_enter": f.notify_enter,
            "notify_exit": f.notify_exit,
            "active_days": f.active_days,
            "active_from": f.active_from.isoformat() if f.active_from else None,
            "active_to": f.active_to.isoformat() if f.active_to else None,
        }
