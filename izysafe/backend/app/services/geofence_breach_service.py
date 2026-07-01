"""Geofence breach detection — the heart of Flow B (CLAUDE.md §5).

Runs in a webhook BackgroundTask (never the hot path, §4). For each position it
classifies the child against every *active* fence, detects enter/exit transitions
against the per-fence Redis state, and — subject to the fence's notify flags, its
schedule, and a 5-minute anti-jitter debounce — records a `geofence_events` row and
fans an alert out to the family via `AlertService`.

Performance (Decision E): the active-fence set + the child's name + the primary
parent's timezone/tier + the child's School Mode config are cached per child in
Redis (`active_fences:{child}`, invalidated by CRUD). The common no-transition ping
then touches Redis only — no DB read. A DB session is opened only on a cache miss or
when a transition actually fires.

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
      • School Mode doesn't suppress it (see below), AND
      • no debounce marker is set for this child+fence.
  On a real fire we set geofence_debounce:{child}:{fence} (5 min).

School Mode (F16, Basic+; Decision G), active when the child has it enabled, the
primary parent is Basic+, and "now" is inside the child's school hours:
  1. a school-zone (zone_type='school') ENTER becomes a `school_arrival` alert;
  2. alerts for NON-school zones are suppressed (state still advances).
`school_absent` detection is deferred to Sprint 6.

Pickup detection (F17, Basic+; Sprint 7) piggybacks on the school-zone EXIT
transition computed here (Decision D5): when a child leaves a school zone inside the
dismissal window (school_hours_to −before/+after, in the primary parent's tz, on a
school day), we record a `pickup_events` row + a `pickup` alert — at most once per
child per day. It reads the RAW exit transition, independent of the geofence's own
notify/schedule/debounce gates, and needs school_hours_to set (no separate
`pickup_enabled` flag — Decision D6). movement_mode is inferred from the fix speed
(Decision D7): ≥ pickup_vehicle_speed_kmh → in_vehicle, else on_foot (unknown if no
speed). It does NOT require School Mode to be enabled.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.geometry import is_inside_circle, is_inside_polygon
from app.models.child import Child, FamilyMember
from app.models.location import Geofence, GeofenceEvent, PickupEvent
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.children_service import effective_tier
from app.services.fcm_gateway import FcmGateway

logger = logging.getLogger("izysafe.geofence")

# School Mode is a Basic+ feature (CLAUDE.md §10). Pickup (F17) shares the gate.
SCHOOL_MODE_TIERS = {"basic", "premium", "school"}
PICKUP_TIERS = SCHOOL_MODE_TIERS


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
        speed: float | None = None,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        bundle = await self._get_bundle(child_id)
        fences = bundle["fences"]
        if not fences:
            return

        school_now = self._school_in_session(bundle, now)

        # (fence, direction, as_school_arrival) tuples that pass every gate.
        to_fire: list[tuple[dict, str, bool]] = []
        pickup_zone: dict | None = None  # a school zone the child just EXITED (F17)
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
            is_school_zone = fence["zone_type"] == "school"
            # Pickup (F17): capture the RAW school-zone exit transition here, before the
            # geofence's own notify/schedule/debounce gates — pickup is independent of them.
            if direction == "exit" and is_school_zone and pickup_zone is None:
                pickup_zone = fence

            if direction == "enter" and not fence["notify_enter"]:
                continue
            if direction == "exit" and not fence["notify_exit"]:
                continue
            if not self._within_schedule(fence, bundle["tz"], now):
                continue

            # School Mode: during school hours, mute non-school zones entirely.
            if school_now and not is_school_zone:
                continue
            if await self.redis.get(rk.geofence_debounce(child_id, fence["id"])):
                continue  # jitter debounce

            as_arrival = school_now and is_school_zone and direction == "enter"
            to_fire.append((fence, direction, as_arrival))

        if to_fire:
            await self._fire(child_id, device_id, lat, lng, bundle["child_name"], to_fire)
        if pickup_zone is not None:
            await self._maybe_record_pickup(
                child_id, pickup_zone, lat, lng, speed, bundle, now
            )

    # --------------------------------------------------------------- internals
    @staticmethod
    def _inside(fence: dict, lat: float, lng: float) -> bool:
        if fence["type"] == "polygon":
            return is_inside_polygon(lat, lng, fence["polygon_points"] or [])
        return is_inside_circle(
            lat, lng, fence["center_lat"], fence["center_lng"], fence["radius_m"]
        )

    @staticmethod
    def _in_window(
        days: list[int], from_iso: str | None, to_iso: str | None, tz_name: str, now: datetime
    ) -> bool:
        """Whether `now` falls within a (active_days, time-range) window, evaluated in
        tz_name. Empty days = every day; no time range = all day. Overnight ranges
        (from > to) are supported."""
        if not days and not from_iso:
            return True
        try:
            local = now.astimezone(ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, ValueError):
            local = now.astimezone(timezone.utc)

        if days and local.isoweekday() not in days:
            return False
        if from_iso and to_iso:
            t = local.time()
            f, u = time.fromisoformat(from_iso), time.fromisoformat(to_iso)
            in_window = f <= t <= u if f <= u else (t >= f or t <= u)
            if not in_window:
                return False
        return True

    def _within_schedule(self, fence: dict, tz_name: str, now: datetime) -> bool:
        """Honor the fence's own active_days + active_from/active_to (parent tz)."""
        return self._in_window(
            fence.get("active_days") or [], fence.get("active_from"),
            fence.get("active_to"), tz_name, now,
        )

    def _school_in_session(self, bundle: dict, now: datetime) -> bool:
        """True when School Mode applies right now: enabled + Basic+ tier + within the
        child's configured school hours (which must be set)."""
        s = bundle["school"]
        if not s["enabled"] or bundle["tier"] not in SCHOOL_MODE_TIERS:
            return False
        if not s["from"] or not s["to"]:
            return False  # hours not configured → nothing to key off
        return self._in_window(s["days"], s["from"], s["to"], bundle["tz"], now)

    # ------------------------------------------------------------- pickup (F17)
    @staticmethod
    def _movement_mode(speed: float | None) -> str:
        """Infer travel mode from the fix speed (Decision D7)."""
        if speed is None:
            return "unknown"
        return "in_vehicle" if speed >= settings.pickup_vehicle_speed_kmh else "on_foot"

    @staticmethod
    def _pickup_window(
        school_to: str | None, school_days: list[int], tz_name: str, now: datetime
    ) -> datetime | None:
        """If `now` falls in the dismissal window (school_hours_to −before/+after) on a
        school day, return the local time; else None. Needs school_hours_to set."""
        if not school_to:
            return None
        try:
            tz = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            tz = timezone.utc
        local = now.astimezone(tz)
        if school_days and local.isoweekday() not in school_days:
            return None
        to_t = time.fromisoformat(school_to)
        dismissal = local.replace(
            hour=to_t.hour, minute=to_t.minute, second=0, microsecond=0
        )
        start = dismissal - timedelta(minutes=settings.pickup_window_before_min)
        end = dismissal + timedelta(minutes=settings.pickup_window_after_min)
        return local if start <= local <= end else None

    async def _maybe_record_pickup(
        self,
        child_id: uuid.UUID,
        zone: dict,
        lat: float,
        lng: float,
        speed: float | None,
        bundle: dict,
        now: datetime,
    ) -> None:
        """Record a pickup for a school-zone exit inside the dismissal window, at most
        once per child per day (Basic+; Decisions D5–D8)."""
        if bundle["tier"] not in PICKUP_TIERS:
            return
        s = bundle["school"]
        local = self._pickup_window(s["to"], s["days"], bundle["tz"], now)
        if local is None:
            return

        day = local.strftime("%Y%m%d")
        dedup_key = rk.pickup_recorded(child_id, day)
        if await self.redis.get(dedup_key):
            return  # already recorded a pickup for this child today

        mode = self._movement_mode(speed)
        async with self.session_factory() as session:
            session.add(
                PickupEvent(
                    child_id=child_id,
                    geofence_id=uuid.UUID(zone["id"]),
                    movement_mode=mode,
                )
            )
            alerts = AlertService(session, self.fcm)
            mode_txt = {"on_foot": "on foot", "in_vehicle": "by vehicle"}.get(
                mode, "movement unknown"
            )
            await alerts.notify_family(
                child_id,
                "pickup",
                f"Pickup from {zone['name']}",
                f"{bundle['child_name']} left {zone['name']} ({mode_txt}).",
                {
                    "geofence_id": zone["id"],
                    "zone_type": zone["zone_type"],
                    "movement_mode": mode,
                    "lat": lat,
                    "lng": lng,
                },
            )
            await session.commit()

        # Set the daily dedup marker only after a successful record (mirrors debounce
        # ordering); expire at the next local midnight so the next school day is fresh.
        midnight = (local + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        ttl = max(1, int((midnight - local).total_seconds()))
        await self.redis.set(dedup_key, "1", ex=ttl)
        logger.info("Pickup recorded for child %s from zone %s (%s)", child_id, zone["id"], mode)

    async def _fire(
        self,
        child_id: uuid.UUID,
        device_id: uuid.UUID | None,
        lat: float,
        lng: float,
        child_name: str,
        to_fire: list[tuple[dict, str, bool]],
    ) -> None:
        async with self.session_factory() as session:
            alerts = AlertService(session, self.fcm)
            for fence, direction, as_arrival in to_fire:
                session.add(
                    GeofenceEvent(
                        child_id=child_id,
                        device_id=device_id,
                        geofence_id=uuid.UUID(fence["id"]),
                        event_type=direction,  # factual ledger: 'enter'/'exit'
                        lat=lat,
                        lng=lng,
                    )
                )
                alert_type, title, body = self._alert_copy(
                    fence, direction, as_arrival, child_name
                )
                await alerts.notify_family(
                    child_id, alert_type, title, body,
                    {
                        "geofence_id": fence["id"],
                        "zone_type": fence["zone_type"],
                        "lat": lat,
                        "lng": lng,
                    },
                )
            await session.commit()

        # Debounce only after a real fire (mirrors speed/battery ordering).
        for fence, direction, _ in to_fire:
            await self.redis.set(
                rk.geofence_debounce(child_id, fence["id"]),
                "1",
                ex=settings.geofence_debounce_seconds,
            )
            logger.info("Geofence %s for child %s (%s)", fence["id"], child_id, direction)

    @staticmethod
    def _alert_copy(
        fence: dict, direction: str, as_arrival: bool, child_name: str
    ) -> tuple[str, str, str]:
        if as_arrival:
            return (
                "school_arrival",
                f"Arrived at {fence['name']}",
                f"{child_name} arrived at {fence['name']}.",
            )
        entered = direction == "enter"
        return (
            "geofence_enter" if entered else "geofence_exit",
            f"{'Entered' if entered else 'Left'} {fence['name']}",
            f"{child_name} {'entered' if entered else 'left'} {fence['name']}.",
        )

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
                "school": {"enabled": False, "from": None, "to": None, "days": []},
                "fences": [self._fence_dict(f) for f in fences],
            }
        child, parent = meta
        return {
            "tz": parent.timezone,
            "child_name": child.name,
            "tier": effective_tier(parent),
            "school": {
                "enabled": child.school_mode_enabled,
                "from": child.school_hours_from.isoformat() if child.school_hours_from else None,
                "to": child.school_hours_to.isoformat() if child.school_hours_to else None,
                "days": child.school_active_days,
            },
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
