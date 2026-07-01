"""Tests for Pickup detection (Sprint 7 Slice 2, F17).

Pickup piggybacks on the school-zone EXIT transition in GeofenceBreachService
(Decision D5). Covers: recording on a school-zone exit inside the dismissal window
(school_hours_to −before/+after, primary-parent tz), movement_mode inference from
speed (D7), once-per-day dedup (D8), the Basic+ tier gate, and the guards
(non-school zone, enter, first-ping baseline, outside window, wrong day, no
school_hours_to, independence from School Mode enabled). Plus webhook wiring.
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
from app.models.location import Geofence, PickupEvent
from app.models.user import User
from app.services.geofence_breach_service import GeofenceBreachService
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway

SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}

# Fixed Wednesday-noon UTC. Dismissal at 12:00 → window [11:30, 13:30] contains NOW.
NOW = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
DOW = NOW.isoweekday()  # 3 (Wed)
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]

CLAT, CLNG = 18.5204, 73.8567
INSIDE = (18.5204, 73.8567)   # school-zone centre
OUTSIDE = (19.0000, 74.0000)  # ~60 km away


async def _setup(
    db, *, tz="UTC", tier="basic", zone_type="school", school_mode=False,
    school_to=time(12, 0), school_days=None, fcm="parent-tok",
):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91",
        subscription_tier=tier, fcm_token=fcm, timezone=tz,
    )
    db.add(parent)
    await db.flush()
    child = Child(
        name="Aryan", school_mode_enabled=school_mode,
        school_hours_from=time(8, 0), school_hours_to=school_to,
        school_active_days=(school_days or ALL_DAYS),
    )
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    fence = Geofence(
        child_id=child.id, name="School", zone_type=zone_type, type="circle",
        center_lat=CLAT, center_lng=CLNG, radius_m=200,
        notify_enter=True, notify_exit=True, active_days=ALL_DAYS, active=True,
    )
    db.add(fence)
    await db.flush()
    return child, parent, fence


def _svc(db, redis, fcm=None):
    return GeofenceBreachService(lambda: NonClosingSession(db), redis, fcm or FakeFcmGateway())


async def _count_pickups(db, child_id):
    return (
        await db.execute(
            select(func.count()).select_from(PickupEvent).where(PickupEvent.child_id == child_id)
        )
    ).scalar_one()


async def _count_alerts(db, child_id, alert_type):
    return (
        await db.execute(
            select(func.count()).select_from(Alert).where(
                Alert.child_id == child_id, Alert.type == alert_type
            )
        )
    ).scalar_one()


async def _exit(svc, child_id, *, speed=None):
    """Baseline inside the school zone, then exit → the pickup-triggering transition."""
    await svc.check_all_fences(child_id, *INSIDE, speed=None, now=NOW)
    await svc.check_all_fences(child_id, *OUTSIDE, speed=speed, now=NOW)


# --------------------------------------------------------------------------- #
# Happy path + movement mode
# --------------------------------------------------------------------------- #
async def test_pickup_recorded_on_foot(db_session, redis_client):
    child, _, fence = await _setup(db_session)
    fcm = FakeFcmGateway()
    svc = _svc(db_session, redis_client, fcm)
    await _exit(svc, child.id, speed=4.0)  # < 10 km/h → on_foot

    assert await _count_pickups(db_session, child.id) == 1
    assert await _count_alerts(db_session, child.id, "pickup") == 1
    ev = (
        await db_session.execute(select(PickupEvent).where(PickupEvent.child_id == child.id))
    ).scalars().one()
    assert ev.movement_mode == "on_foot"
    assert ev.geofence_id == fence.id
    assert fcm.calls[-1]["data"]["type"] == "pickup"
    assert fcm.calls[-1]["data"]["movement_mode"] == "on_foot"
    # dedup marker set for today
    assert await redis_client.get(rk.pickup_recorded(child.id, "20260617")) == "1"


async def test_pickup_in_vehicle(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=45.0)  # ≥ 10 km/h → in_vehicle
    ev = (
        await db_session.execute(select(PickupEvent).where(PickupEvent.child_id == child.id))
    ).scalars().one()
    assert ev.movement_mode == "in_vehicle"


async def test_pickup_unknown_speed(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=None)
    ev = (
        await db_session.execute(select(PickupEvent).where(PickupEvent.child_id == child.id))
    ).scalars().one()
    assert ev.movement_mode == "unknown"


async def test_pickup_independent_of_school_mode_enabled(db_session, redis_client):
    # School Mode OFF but school_hours_to set → pickup still records (Decision D6).
    child, _, _ = await _setup(db_session, school_mode=False)
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)
    assert await _count_pickups(db_session, child.id) == 1


async def test_pickup_with_school_mode_on(db_session, redis_client):
    child, _, _ = await _setup(db_session, school_mode=True)
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)
    assert await _count_pickups(db_session, child.id) == 1


# --------------------------------------------------------------------------- #
# Dedup (once per child per day)
# --------------------------------------------------------------------------- #
async def test_pickup_deduped_same_day(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)                 # first pickup
    await svc.check_all_fences(child.id, *INSIDE, now=NOW)   # re-enter
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)  # exit again → deduped
    assert await _count_pickups(db_session, child.id) == 1


# --------------------------------------------------------------------------- #
# Window / schedule guards
# --------------------------------------------------------------------------- #
async def test_pickup_outside_window_after(db_session, redis_client):
    # Dismissal 08:00 → window [07:30, 09:30]; NOW=12:00 is well after → no pickup.
    child, _, _ = await _setup(db_session, school_to=time(8, 0))
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)
    assert await _count_pickups(db_session, child.id) == 0
    # but the school-zone exit still produced a generic geofence_exit alert
    assert await _count_alerts(db_session, child.id, "geofence_exit") == 1


async def test_pickup_outside_window_before(db_session, redis_client):
    # Dismissal 15:00 → window [14:30, 16:30]; NOW=12:00 is before → no pickup.
    child, _, _ = await _setup(db_session, school_to=time(15, 0))
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)
    assert await _count_pickups(db_session, child.id) == 0


async def test_pickup_wrong_day(db_session, redis_client):
    other_days = [d for d in ALL_DAYS if d != DOW]
    child, _, _ = await _setup(db_session, school_days=other_days)
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)
    assert await _count_pickups(db_session, child.id) == 0


async def test_pickup_uses_parent_timezone(db_session, redis_client):
    # NOW=12:00 UTC = 17:30 IST. Dismissal 17:30 IST → window contains NOW only when
    # evaluated in IST, proving the parent timezone is honored.
    child, _, _ = await _setup(db_session, tz="Asia/Kolkata", school_to=time(17, 30))
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)
    assert await _count_pickups(db_session, child.id) == 1


async def test_pickup_requires_school_hours_to(db_session, redis_client):
    child, _, _ = await _setup(db_session, school_to=None)
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)
    assert await _count_pickups(db_session, child.id) == 0


# --------------------------------------------------------------------------- #
# Trigger guards
# --------------------------------------------------------------------------- #
async def test_pickup_only_school_zone(db_session, redis_client):
    child, _, _ = await _setup(db_session, zone_type="home")  # not a school zone
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)
    assert await _count_pickups(db_session, child.id) == 0


async def test_pickup_not_on_enter(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, now=NOW)  # baseline outside
    await svc.check_all_fences(child.id, *INSIDE, speed=4.0, now=NOW)  # enter, not exit
    assert await _count_pickups(db_session, child.id) == 0


async def test_pickup_not_on_first_ping(db_session, redis_client):
    child, _, _ = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.check_all_fences(child.id, *OUTSIDE, speed=4.0, now=NOW)  # baseline, no transition
    assert await _count_pickups(db_session, child.id) == 0


async def test_pickup_free_tier_blocked(db_session, redis_client):
    child, _, _ = await _setup(db_session, tier="free")
    svc = _svc(db_session, redis_client)
    await _exit(svc, child.id, speed=4.0)
    assert await _count_pickups(db_session, child.id) == 0


# --------------------------------------------------------------------------- #
# Webhook wiring (school_to pinned to the real current time so it's deterministic)
# --------------------------------------------------------------------------- #
async def _device(db, child_id, traccar_id):
    dev = Device(
        child_id=child_id, name="Watch", device_type="watch",
        imei=uuid.uuid4().hex[:15], traccar_id=traccar_id,
    )
    db.add(dev)
    await db.flush()
    return dev


def _payload(traccar_id, imei, lat, lng, speed_knots=None):
    pos = {
        "deviceId": traccar_id, "latitude": lat, "longitude": lng,
        "valid": True, "attributes": {},
    }
    if speed_knots is not None:
        pos["speed"] = speed_knots
    return {"position": pos, "device": {"id": traccar_id, "uniqueId": imei}}


async def test_webhook_triggers_pickup(client, db_session, redis_client, fake_fcm_gateway):
    now_local = datetime.now(timezone.utc)
    child, _, _ = await _setup(
        db_session, tz="UTC",
        school_to=now_local.time().replace(second=0, microsecond=0),
        school_days=ALL_DAYS,
    )
    dev = await _device(db_session, child.id, 501)

    await client.post("/api/v1/webhook/traccar", headers=SECRET_HEADERS,
                      json=_payload(501, dev.imei, *INSIDE))          # baseline inside
    await client.post("/api/v1/webhook/traccar", headers=SECRET_HEADERS,
                      json=_payload(501, dev.imei, *OUTSIDE, speed_knots=30))  # exit by vehicle

    assert await _count_pickups(db_session, child.id) == 1
    ev = (
        await db_session.execute(select(PickupEvent).where(PickupEvent.child_id == child.id))
    ).scalars().one()
    assert ev.movement_mode == "in_vehicle"  # 30 knots ≈ 55 km/h
    assert fake_fcm_gateway.calls[-1]["data"]["type"] == "pickup"
