"""Tests for geofence breach detection (Sprint 3 Slice 3) — Flow B.

Covers the enter/exit state machine, baseline (no first-ping alert), notify-flag
suppression, the 5-min debounce, schedule honoring (active_days + time window in the
primary parent's timezone — Decision C), polygon zones, the active-fence cache +
CRUD invalidation (Decision E), inactive/multi-fence handling, and the webhook
wiring incl. stale-fix suppression.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select

from app.core import redis_keys as rk
from app.core.config import settings
from app.models.alert import Alert
from app.models.child import Child, FamilyMember
from app.models.device import Device
from app.models.location import Geofence, GeofenceEvent
from app.models.user import User
from app.services.geofence_breach_service import GeofenceBreachService
from app.services.geofence_service import GeofenceService
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway

SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}

# A fixed Wednesday-noon UTC instant so schedule tests don't depend on the run day.
NOW = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
DOW = NOW.isoweekday()  # 3 (Wed)
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]

CLAT, CLNG = 18.5204, 73.8567   # circle centre
INSIDE = (18.5204, 73.8567)      # the centre — unambiguously inside r=200m
OUTSIDE = (19.0000, 74.0000)     # ~60 km away

# Square polygon ~ (18.50–18.60, 73.80–73.90)
SQUARE = [
    {"lat": 18.50, "lng": 73.80},
    {"lat": 18.50, "lng": 73.90},
    {"lat": 18.60, "lng": 73.90},
    {"lat": 18.60, "lng": 73.80},
]
IN_POLY = (18.55, 73.85)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _setup(
    db, *, tz="UTC", fcm="parent-tok", fence=True, tier="premium",
    school_mode=False, school_from=None, school_to=None, school_days=None, **fence_kw,
):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91",
        subscription_tier=tier, fcm_token=fcm, timezone=tz,
    )
    db.add(parent)
    await db.flush()
    child = Child(
        name="Aryan", school_mode_enabled=school_mode,
        school_hours_from=school_from, school_hours_to=school_to,
        school_active_days=(school_days or ALL_DAYS),
    )
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    await db.flush()

    f = None
    if fence:
        defaults = dict(
            name="Home", zone_type="home", type="circle",
            center_lat=CLAT, center_lng=CLNG, radius_m=200,
            notify_enter=True, notify_exit=True, active_days=ALL_DAYS, active=True,
        )
        defaults.update(fence_kw)
        f = Geofence(child_id=child.id, **defaults)
        db.add(f)
        await db.flush()
    return child, parent, f


def _svc(db, redis, fcm=None):
    return GeofenceBreachService(lambda: NonClosingSession(db), redis, fcm or FakeFcmGateway())


async def _count_alerts(db, child_id, alert_type):
    return (
        await db.execute(
            select(func.count()).select_from(Alert).where(
                Alert.child_id == child_id, Alert.type == alert_type
            )
        )
    ).scalar_one()


async def _count_events(db, child_id, event_type=None):
    stmt = select(func.count()).select_from(GeofenceEvent).where(
        GeofenceEvent.child_id == child_id
    )
    if event_type:
        stmt = stmt.where(GeofenceEvent.event_type == event_type)
    return (await db.execute(stmt)).scalar_one()


# --------------------------------------------------------------------------- #
# State machine: baseline + transitions
# --------------------------------------------------------------------------- #
async def test_first_ping_is_baseline_no_alert(db_session, redis_client):
    child, _, fence = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)

    assert await _count_events(db_session, child.id) == 0
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0
    # state recorded for next time
    assert await redis_client.get(rk.geofence_inside(child.id, fence.id)) == "true"


async def test_enter_transition_fires(db_session, redis_client):
    child, _, fence = await _setup(db_session)
    fcm = FakeFcmGateway()
    svc = _svc(db_session, redis_client, fcm)

    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)   # baseline outside
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)    # → enter

    assert await _count_events(db_session, child.id, "enter") == 1
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1
    assert fcm.calls[-1]["data"]["type"] == "geofence_enter"
    assert fcm.calls[-1]["data"]["geofence_id"] == str(fence.id)
    assert fcm.calls[-1]["tokens"] == ["parent-tok"]
    assert await redis_client.get(rk.geofence_debounce(child.id, fence.id)) == "1"


async def test_exit_transition_fires(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)

    await svc.check_all_fences(child.id, *INSIDE, now=NOW)    # baseline inside
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)   # → exit

    assert await _count_events(db_session, child.id, "exit") == 1
    assert await _count_alerts(db_session, child.id, "geofence_exit") == 1


async def test_staying_inside_no_repeat(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0


# --------------------------------------------------------------------------- #
# Notify-flag suppression (state still advances)
# --------------------------------------------------------------------------- #
async def test_notify_enter_off_suppresses(db_session, redis_client):
    child, _, fence = await _setup(db_session, notify_enter=False)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0
    assert await redis_client.get(rk.geofence_inside(child.id, fence.id)) == "true"


async def test_notify_exit_off_suppresses(db_session, redis_client):
    child, _, _ = await _setup(db_session, notify_exit=False)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_exit") == 0


# --------------------------------------------------------------------------- #
# Debounce
# --------------------------------------------------------------------------- #
async def test_debounce_suppresses_jitter(db_session, redis_client):
    child, _, fence = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)   # baseline
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)    # enter → fires + debounce
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)   # exit within debounce → suppressed

    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1
    assert await _count_alerts(db_session, child.id, "geofence_exit") == 0
    # state still tracks reality even though the alert was debounced
    assert await redis_client.get(rk.geofence_inside(child.id, fence.id)) == "false"


# --------------------------------------------------------------------------- #
# Schedule honoring (Decision C: primary parent's timezone)
# --------------------------------------------------------------------------- #
async def test_schedule_day_excluded_suppresses(db_session, redis_client):
    other_days = [d for d in ALL_DAYS if d != DOW]
    child, _, fence = await _setup(db_session, active_days=other_days)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0
    # state advanced despite suppression
    assert await redis_client.get(rk.geofence_inside(child.id, fence.id)) == "true"


async def test_schedule_day_included_fires(db_session, redis_client):
    child, _, _ = await _setup(db_session, active_days=[DOW])
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1


async def test_schedule_time_window_outside_suppresses(db_session, redis_client):
    # tz=UTC, NOW=12:00; window 13:00–17:00 excludes noon.
    child, _, _ = await _setup(
        db_session, tz="UTC", active_days=ALL_DAYS,
        active_from=time(13, 0), active_to=time(17, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0


async def test_schedule_time_window_inside_fires(db_session, redis_client):
    child, _, _ = await _setup(
        db_session, tz="UTC", active_days=ALL_DAYS,
        active_from=time(8, 0), active_to=time(15, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1


async def test_schedule_uses_parent_timezone(db_session, redis_client):
    # NOW=12:00 UTC = 17:30 IST. A 17:00–18:00 window only contains it in IST,
    # so firing proves the window was evaluated in the parent's timezone, not UTC.
    child, _, _ = await _setup(
        db_session, tz="Asia/Kolkata", active_days=ALL_DAYS,
        active_from=time(17, 0), active_to=time(18, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1


# --------------------------------------------------------------------------- #
# Polygon zones
# --------------------------------------------------------------------------- #
async def test_polygon_enter_fires(db_session, redis_client):
    child, _, _ = await _setup(
        db_session, fence=False,
    )
    db_session.add(Geofence(
        child_id=child.id, name="Yard", zone_type="other", type="polygon",
        polygon_points=SQUARE, notify_enter=True, notify_exit=True, active_days=ALL_DAYS,
    ))
    await db_session.flush()
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *IN_POLY, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1


# --------------------------------------------------------------------------- #
# Multi-fence / inactive
# --------------------------------------------------------------------------- #
async def test_only_crossed_fence_fires(db_session, redis_client):
    child, _, home = await _setup(db_session)  # Home circle at CLAT/CLNG
    school = Geofence(
        child_id=child.id, name="School", zone_type="school", type="circle",
        center_lat=19.20, center_lng=72.90, radius_m=200, active_days=ALL_DAYS,
    )
    db_session.add(school)
    await db_session.flush()

    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)  # baseline: outside both
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)   # enter Home only

    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1
    ev = (
        await db_session.execute(
            select(GeofenceEvent).where(GeofenceEvent.child_id == child.id)
        )
    ).scalars().all()
    assert len(ev) == 1 and ev[0].geofence_id == home.id


async def test_inactive_fence_ignored(db_session, redis_client):
    child, _, _ = await _setup(db_session, active=False)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0


async def test_no_fences_is_noop(db_session, redis_client):
    child, _, _ = await _setup(db_session, fence=False)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)  # must not raise
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0


# --------------------------------------------------------------------------- #
# Active-fence cache (Decision E)
# --------------------------------------------------------------------------- #
async def test_bundle_is_cached(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await redis_client.get(rk.active_fences(child.id)) is not None


async def test_crud_invalidates_cache(db_session, redis_client):
    child, parent, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await redis_client.get(rk.active_fences(child.id)) is not None

    # Creating a zone through the CRUD service must drop the cache.
    await GeofenceService(db_session, redis_client).create_geofence(
        parent, child.id,
        {"name": "Park", "type": "circle", "center_lat": 18.4, "center_lng": 73.7, "radius_m": 150},
    )
    assert await redis_client.get(rk.active_fences(child.id)) is None


# --------------------------------------------------------------------------- #
# School Mode (F16, Basic+; Decision G). NOW = Wed 12:00 UTC.
# --------------------------------------------------------------------------- #
async def test_school_zone_enter_in_hours_is_arrival(db_session, redis_client):
    child, _, _ = await _setup(
        db_session, tier="basic", zone_type="school", name="School",
        school_mode=True, school_from=time(8, 0), school_to=time(15, 0),
    )
    fcm = FakeFcmGateway()
    svc = _svc(db_session, redis_client, fcm)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)

    assert await _count_alerts(db_session, child.id, "school_arrival") == 1
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0
    assert await _count_events(db_session, child.id, "enter") == 1  # ledger unchanged
    assert fcm.calls[-1]["data"]["type"] == "school_arrival"


async def test_school_zone_enter_outside_hours_is_generic(db_session, redis_client):
    child, _, _ = await _setup(
        db_session, tier="basic", zone_type="school", name="School",
        school_mode=True, school_from=time(13, 0), school_to=time(15, 0),  # excludes noon
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1
    assert await _count_alerts(db_session, child.id, "school_arrival") == 0


async def test_non_school_zone_suppressed_in_hours(db_session, redis_client):
    child, _, fence = await _setup(
        db_session, tier="basic", zone_type="home", name="Home",
        school_mode=True, school_from=time(8, 0), school_to=time(15, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0
    # state still advanced despite the School-Mode suppression
    assert await redis_client.get(rk.geofence_inside(child.id, fence.id)) == "true"


async def test_non_school_zone_not_suppressed_outside_hours(db_session, redis_client):
    child, _, _ = await _setup(
        db_session, tier="basic", zone_type="home", name="Home",
        school_mode=True, school_from=time(13, 0), school_to=time(15, 0),  # excludes noon
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1


async def test_school_mode_ignored_on_free_tier(db_session, redis_client):
    child, _, _ = await _setup(
        db_session, tier="free", zone_type="school", name="School",
        school_mode=True, school_from=time(8, 0), school_to=time(15, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    # Free tier → no School Mode: generic enter, no arrival upgrade.
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1
    assert await _count_alerts(db_session, child.id, "school_arrival") == 0


async def test_school_mode_disabled_is_generic(db_session, redis_client):
    child, _, _ = await _setup(
        db_session, tier="basic", zone_type="school", name="School",
        school_mode=False, school_from=time(8, 0), school_to=time(15, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1
    assert await _count_alerts(db_session, child.id, "school_arrival") == 0


async def test_school_zone_exit_in_hours_is_generic(db_session, redis_client):
    child, _, _ = await _setup(
        db_session, tier="basic", zone_type="school", name="School",
        school_mode=True, school_from=time(8, 0), school_to=time(15, 0),
    )
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)    # baseline inside
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)   # exit
    # Exit isn't an arrival, and school zones are exempt from suppression.
    assert await _count_alerts(db_session, child.id, "geofence_exit") == 1
    assert await _count_alerts(db_session, child.id, "school_arrival") == 0


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


async def test_webhook_triggers_geofence_enter(client, db_session, redis_client, fake_fcm_gateway):
    # tz=UTC + all-days fence so the real "now" never falls outside the schedule.
    child, _, _ = await _setup(db_session, tz="UTC")
    dev = await _device(db_session, child.id, 301)

    assert (await _post(client, _payload(301, dev.imei, *OUTSIDE))).json()["status"] == "accepted"
    assert (await _post(client, _payload(301, dev.imei, *INSIDE))).json()["status"] == "accepted"

    assert await _count_alerts(db_session, child.id, "geofence_enter") == 1
    assert fake_fcm_gateway.calls[-1]["data"]["type"] == "geofence_enter"


async def test_webhook_stale_fix_skips_geofence(client, db_session, redis_client, fake_fcm_gateway):
    child, _, _ = await _setup(db_session, tz="UTC")
    dev = await _device(db_session, child.id, 302)

    stale = datetime.now(timezone.utc) - timedelta(minutes=10)
    await _post(client, _payload(302, dev.imei, *OUTSIDE))
    resp = await _post(client, _payload(302, dev.imei, *INSIDE, fix_time=stale))
    assert resp.json()["stale"] is True

    # Stale position must not raise a fresh enter alert.
    assert await _count_alerts(db_session, child.id, "geofence_enter") == 0
