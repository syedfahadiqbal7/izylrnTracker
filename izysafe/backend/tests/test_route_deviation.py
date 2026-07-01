"""Tests for Safe Route deviation detection (Sprint 7 Slice 1, F20).

Covers the on-route/off-route state machine (baseline → transition), the tolerance
boundary, return-to-route re-arming, the 5-min debounce, schedule honoring
(active_days + time window in the primary parent's timezone), the Premium tier gate
(free/lapsed → inert), inactive/multi-route handling, the active-route cache + CRUD
invalidation, and the webhook wiring incl. stale-fix suppression.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from app.core import redis_keys as rk
from app.core.config import settings
from app.models.alert import Alert
from app.models.child import Child, FamilyMember
from app.models.device import Device
from app.models.route import SafeRoute
from app.models.user import User
from app.services.route_deviation_service import RouteDeviationService
from app.services.route_service import RouteService
from sqlalchemy import func, select
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway

SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}

# A fixed Wednesday-noon UTC instant so schedule tests don't depend on the run day.
NOW = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
DOW = NOW.isoweekday()  # 3 (Wed)
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]

# Route: an east-west segment at latitude 18.5200 (lng 73.85 → 73.86).
ROUTE_WPS = [
    {"lat": 18.5200, "lng": 73.8500, "name": "Home"},
    {"lat": 18.5200, "lng": 73.8600, "name": "School"},
]
ON_ROUTE = (18.5200, 73.8550)     # on the segment → distance ≈ 0
NEAR_ROUTE = (18.5210, 73.8550)   # ~111 m north → within a 200 m tolerance
OFF_ROUTE = (18.5300, 73.8550)    # ~1.1 km north → outside tolerance

# A second, far-north route (~8.9 km away) for multi-route isolation.
ROUTE_B_WPS = [
    {"lat": 18.6000, "lng": 73.8500},
    {"lat": 18.6000, "lng": 73.8600},
]

# A wide window covering any wall-clock time (for real-`now` webhook tests).
ALLDAY = dict(active_from=time(0, 0), active_to=time(23, 59))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _setup(
    db, *, tz="UTC", fcm="parent-tok", route=True, tier="premium", expires=None,
    waypoints=None, tolerance=200, active_days=None,
    active_from=time(0, 0), active_to=time(23, 59), active=True,
):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91",
        subscription_tier=tier, subscription_expires_at=expires,
        fcm_token=fcm, timezone=tz,
    )
    db.add(parent)
    await db.flush()
    child = Child(name="Aryan")
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    await db.flush()

    r = None
    if route:
        r = SafeRoute(
            child_id=child.id, name="School run",
            waypoints=(waypoints or ROUTE_WPS), deviation_tolerance_m=tolerance,
            active_days=(active_days or ALL_DAYS),
            active_from=active_from, active_to=active_to, active=active,
        )
        db.add(r)
        await db.flush()
    return child, parent, r


def _svc(db, redis, fcm=None):
    return RouteDeviationService(lambda: NonClosingSession(db), redis, fcm or FakeFcmGateway())


async def _count_alerts(db, child_id):
    return (
        await db.execute(
            select(func.count()).select_from(Alert).where(
                Alert.child_id == child_id, Alert.type == "route_deviation"
            )
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# State machine: baseline + transitions
# --------------------------------------------------------------------------- #
async def test_first_ping_off_route_is_baseline_no_alert(db_session, redis_client):
    child, _, route = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)

    assert await _count_alerts(db_session, child.id) == 0
    # state recorded for next time
    assert await redis_client.get(rk.route_deviating(child.id, route.id)) == "true"


async def test_deviation_transition_fires(db_session, redis_client):
    child, _, route = await _setup(db_session)
    fcm = FakeFcmGateway()
    svc = _svc(db_session, redis_client, fcm)

    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)   # baseline on-route
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)  # → deviation

    assert await _count_alerts(db_session, child.id) == 1
    assert fcm.calls[-1]["data"]["type"] == "route_deviation"
    assert fcm.calls[-1]["data"]["route_id"] == str(route.id)
    assert fcm.calls[-1]["data"]["distance_m"] > 200
    assert fcm.calls[-1]["tokens"] == ["parent-tok"]
    assert await redis_client.get(rk.route_debounce(child.id, route.id)) == "1"


async def test_return_to_route_no_alert(db_session, redis_client):
    child, _, route = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)  # baseline off-route
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)   # returned → re-arm silently

    assert await _count_alerts(db_session, child.id) == 0
    assert await redis_client.get(rk.route_deviating(child.id, route.id)) == "false"


async def test_staying_off_route_no_repeat(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)   # baseline on
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)  # deviation → 1 alert
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)  # still off → no change
    assert await _count_alerts(db_session, child.id) == 1


async def test_within_tolerance_is_on_route(db_session, redis_client):
    child, _, route = await _setup(db_session, tolerance=200)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)     # baseline on
    await svc.check_all_routes(child.id, *NEAR_ROUTE, now=NOW)   # ~111 m < 200 → still on
    assert await _count_alerts(db_session, child.id) == 0
    assert await redis_client.get(rk.route_deviating(child.id, route.id)) == "false"


async def test_tighter_tolerance_flags_near_point(db_session, redis_client):
    # Same ~111 m offset, but a 100 m tolerance now counts as a deviation.
    child, _, _ = await _setup(db_session, tolerance=100)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    await svc.check_all_routes(child.id, *NEAR_ROUTE, now=NOW)
    assert await _count_alerts(db_session, child.id) == 1


# --------------------------------------------------------------------------- #
# Debounce
# --------------------------------------------------------------------------- #
async def test_debounce_suppresses_jitter(db_session, redis_client):
    child, _, route = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)    # baseline
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)   # deviation → fires + debounce
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)    # back on → re-arm (no alert)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)   # deviation within debounce → suppressed

    assert await _count_alerts(db_session, child.id) == 1
    # state still tracks reality even though the second alert was debounced
    assert await redis_client.get(rk.route_deviating(child.id, route.id)) == "true"


# --------------------------------------------------------------------------- #
# Schedule honoring (primary parent's timezone)
# --------------------------------------------------------------------------- #
async def test_schedule_day_excluded_suppresses(db_session, redis_client):
    other_days = [d for d in ALL_DAYS if d != DOW]
    child, _, route = await _setup(db_session, active_days=other_days)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)
    assert await _count_alerts(db_session, child.id) == 0
    # state advanced despite suppression
    assert await redis_client.get(rk.route_deviating(child.id, route.id)) == "true"


async def test_schedule_day_included_fires(db_session, redis_client):
    child, _, _ = await _setup(db_session, active_days=[DOW])
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)
    assert await _count_alerts(db_session, child.id) == 1


async def test_schedule_time_window_outside_suppresses(db_session, redis_client):
    # tz=UTC, NOW=12:00; window 13:00–17:00 excludes noon.
    child, _, _ = await _setup(
        db_session, tz="UTC", active_from=time(13, 0), active_to=time(17, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)
    assert await _count_alerts(db_session, child.id) == 0


async def test_schedule_time_window_inside_fires(db_session, redis_client):
    child, _, _ = await _setup(
        db_session, tz="UTC", active_from=time(8, 0), active_to=time(15, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)
    assert await _count_alerts(db_session, child.id) == 1


async def test_schedule_uses_parent_timezone(db_session, redis_client):
    # NOW=12:00 UTC = 17:30 IST. A 17:00–18:00 window only contains it in IST.
    child, _, _ = await _setup(
        db_session, tz="Asia/Kolkata", active_from=time(17, 0), active_to=time(18, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)
    assert await _count_alerts(db_session, child.id) == 1


# --------------------------------------------------------------------------- #
# Tier gate (Premium)
# --------------------------------------------------------------------------- #
async def test_free_tier_no_detection(db_session, redis_client):
    child, _, _ = await _setup(db_session, tier="free")
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)
    assert await _count_alerts(db_session, child.id) == 0


async def test_lapsed_premium_no_detection(db_session, redis_client):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    child, _, _ = await _setup(db_session, tier="premium", expires=past)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)
    assert await _count_alerts(db_session, child.id) == 0


# --------------------------------------------------------------------------- #
# Inactive / multi-route
# --------------------------------------------------------------------------- #
async def test_inactive_route_ignored(db_session, redis_client):
    child, _, _ = await _setup(db_session, active=False)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)
    assert await _count_alerts(db_session, child.id) == 0


async def test_no_routes_is_noop(db_session, redis_client):
    child, _, _ = await _setup(db_session, route=False)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)  # must not raise
    assert await _count_alerts(db_session, child.id) == 0


async def test_only_deviated_route_fires(db_session, redis_client):
    child, _, route_a = await _setup(db_session)  # east-west route at lat 18.52
    route_b = SafeRoute(
        child_id=child.id, name="Far route", waypoints=ROUTE_B_WPS,
        deviation_tolerance_m=200, active_days=ALL_DAYS,
        active_from=time(0, 0), active_to=time(23, 59), active=True,
    )
    db_session.add(route_b)
    await db_session.flush()

    svc = _svc(db_session, redis_client)
    # Baseline: on route A, far from route B (A=on, B=off).
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    # Move off route A (still far from B): A on→off fires; B stays off (no change).
    await svc.check_all_routes(child.id, *OFF_ROUTE, now=NOW)

    assert await _count_alerts(db_session, child.id) == 1
    alert = (
        await db_session.execute(
            select(Alert).where(Alert.child_id == child.id, Alert.type == "route_deviation")
        )
    ).scalars().one()
    assert alert.data["route_id"] == str(route_a.id)


# --------------------------------------------------------------------------- #
# Active-route cache
# --------------------------------------------------------------------------- #
async def test_bundle_is_cached(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    assert await redis_client.get(rk.active_routes(child.id)) is not None


async def test_crud_invalidates_cache(db_session, redis_client):
    child, parent, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_routes(child.id, *ON_ROUTE, now=NOW)
    assert await redis_client.get(rk.active_routes(child.id)) is not None

    # Creating a route through the CRUD service must drop the cache.
    await RouteService(db_session, redis_client).create_route(
        parent, child.id,
        {
            "name": "New", "waypoints": ROUTE_WPS, "deviation_tolerance_m": 200,
            "active_days": ALL_DAYS, "active_from": time(0, 0), "active_to": time(23, 59),
        },
    )
    assert await redis_client.get(rk.active_routes(child.id)) is None


# --------------------------------------------------------------------------- #
# Webhook wiring
# --------------------------------------------------------------------------- #
def _payload(traccar_id, imei, lat, lng, fix_time=None):
    pos = {
        "deviceId": traccar_id, "latitude": lat, "longitude": lng,
        "valid": True, "attributes": {},
    }
    if fix_time is not None:
        pos["fixTime"] = fix_time.isoformat()
    return {"position": pos, "device": {"id": traccar_id, "uniqueId": imei}}


async def _device(db, child_id, traccar_id):
    dev = Device(
        child_id=child_id, name="Watch", device_type="watch",
        imei=uuid.uuid4().hex[:15], traccar_id=traccar_id,
    )
    db.add(dev)
    await db.flush()
    return dev


async def _post(client, payload):
    return await client.post("/api/v1/webhook/traccar", headers=SECRET_HEADERS, json=payload)


async def test_webhook_triggers_route_deviation(client, db_session, redis_client, fake_fcm_gateway):
    # tz=UTC + all-day window so the real "now" never falls outside the schedule.
    child, _, _ = await _setup(db_session, tz="UTC")
    dev = await _device(db_session, child.id, 401)

    assert (await _post(client, _payload(401, dev.imei, *ON_ROUTE))).json()["status"] == "accepted"
    assert (await _post(client, _payload(401, dev.imei, *OFF_ROUTE))).json()["status"] == "accepted"

    assert await _count_alerts(db_session, child.id) == 1
    assert fake_fcm_gateway.calls[-1]["data"]["type"] == "route_deviation"


async def test_webhook_stale_fix_skips_route(client, db_session, redis_client, fake_fcm_gateway):
    child, _, _ = await _setup(db_session, tz="UTC")
    dev = await _device(db_session, child.id, 402)

    stale = datetime.now(timezone.utc) - timedelta(minutes=10)
    await _post(client, _payload(402, dev.imei, *ON_ROUTE))
    resp = await _post(client, _payload(402, dev.imei, *OFF_ROUTE, fix_time=stale))
    assert resp.json()["stale"] is True

    # Stale position must not raise a fresh deviation alert.
    assert await _count_alerts(db_session, child.id) == 0
