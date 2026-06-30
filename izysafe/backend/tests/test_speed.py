"""Tests for speed alerts (Sprint 2, Slice 6).

Covers windowed sustained-sample firing, reset on slowdown, debounce, tier gating,
the per-child enable toggle + threshold, and the webhook wiring.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core import redis_keys as rk
from app.core.config import settings
from app.models.alert import Alert
from app.models.child import Child, FamilyMember
from app.models.device import Device
from app.models.user import User
from app.services.speed_service import SpeedService
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway

SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}
N = settings.speed_required_samples  # 3


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _setup(db, *, tier="basic", enabled=True, threshold=60, fcm="parent-tok"):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91",
        subscription_tier=tier, fcm_token=fcm,
    )
    db.add(parent)
    await db.flush()
    child = Child(name="Aryan", speed_alert_enabled=enabled, speed_threshold_kmh=threshold)
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    await db.flush()
    return child, parent


def _svc(db_session, redis, fcm):
    return SpeedService(lambda: NonClosingSession(db_session), redis, fcm)


async def _speed_alerts(db, child_id):
    return (
        await db.execute(
            select(func.count()).select_from(Alert).where(
                Alert.child_id == child_id, Alert.type == "speed"
            )
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Windowed sustained samples
# --------------------------------------------------------------------------- #
async def test_single_sample_does_not_fire(db_session, redis_client):
    child, _ = await _setup(db_session)
    await _svc(db_session, redis_client, FakeFcmGateway()).evaluate(child.id, 75)
    assert await _speed_alerts(db_session, child.id) == 0
    assert await redis_client.get(rk.speed_count(child.id)) == "1"


async def test_three_sustained_samples_fire(db_session, redis_client):
    child, _ = await _setup(db_session, threshold=60)
    fcm = FakeFcmGateway()
    svc = _svc(db_session, redis_client, fcm)
    for _ in range(N):
        await svc.evaluate(child.id, 75)

    assert await _speed_alerts(db_session, child.id) == 1
    assert fcm.calls[-1]["data"]["type"] == "speed"
    assert fcm.calls[-1]["tokens"] == ["parent-tok"]
    assert await redis_client.get(rk.speed_alerted(child.id)) == "1"


async def test_slowdown_resets_counter(db_session, redis_client):
    child, _ = await _setup(db_session, threshold=60)
    svc = _svc(db_session, redis_client, FakeFcmGateway())
    await svc.evaluate(child.id, 70)
    await svc.evaluate(child.id, 70)
    await svc.evaluate(child.id, 40)   # below threshold → reset
    assert await redis_client.get(rk.speed_count(child.id)) is None
    await svc.evaluate(child.id, 70)
    await svc.evaluate(child.id, 70)
    assert await _speed_alerts(db_session, child.id) == 0   # only 2 since reset
    await svc.evaluate(child.id, 70)
    assert await _speed_alerts(db_session, child.id) == 1   # 3rd → fires


async def test_debounced_after_firing(db_session, redis_client):
    child, _ = await _setup(db_session, threshold=60)
    svc = _svc(db_session, redis_client, FakeFcmGateway())
    for _ in range(N + 3):   # well past the threshold count
        await svc.evaluate(child.id, 80)
    assert await _speed_alerts(db_session, child.id) == 1   # debounce → single alert


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #
async def test_free_tier_gated_out(db_session, redis_client):
    child, _ = await _setup(db_session, tier="free", threshold=60)
    svc = _svc(db_session, redis_client, FakeFcmGateway())
    for _ in range(N):
        await svc.evaluate(child.id, 90)
    assert await _speed_alerts(db_session, child.id) == 0
    assert await redis_client.get(rk.speed_count(child.id)) is None  # never counted


async def test_disabled_toggle_gated_out(db_session, redis_client):
    child, _ = await _setup(db_session, enabled=False, threshold=60)
    svc = _svc(db_session, redis_client, FakeFcmGateway())
    for _ in range(N):
        await svc.evaluate(child.id, 90)
    assert await _speed_alerts(db_session, child.id) == 0


async def test_per_child_threshold_respected(db_session, redis_client):
    child, _ = await _setup(db_session, threshold=80)   # higher limit
    svc = _svc(db_session, redis_client, FakeFcmGateway())
    for _ in range(N):
        await svc.evaluate(child.id, 70)   # under 80 → no alert
    assert await _speed_alerts(db_session, child.id) == 0
    assert await redis_client.get(rk.speed_count(child.id)) is None


# --------------------------------------------------------------------------- #
# Webhook wiring
# --------------------------------------------------------------------------- #
async def test_webhook_triggers_speed_alert(client, db_session, redis_client, fake_fcm_gateway):
    child, _ = await _setup(db_session, threshold=60)
    dev = Device(
        child_id=child.id, name="Watch", device_type="watch",
        imei=uuid.uuid4().hex[:15], traccar_id=205,
    )
    db_session.add(dev)
    await db_session.flush()

    # 40 knots ≈ 74 km/h, over the 60 threshold; three sustained pings.
    payload = {
        "position": {
            "deviceId": 205, "latitude": 25.2, "longitude": 55.3,
            "speed": 40.0, "valid": True, "attributes": {},
        },
        "device": {"id": 205, "uniqueId": dev.imei},
    }
    for _ in range(N):
        resp = await client.post("/api/v1/webhook/traccar", headers=SECRET_HEADERS, json=payload)
        assert resp.json()["status"] == "accepted"

    assert await _speed_alerts(db_session, child.id) == 1
    assert fake_fcm_gateway.calls[-1]["data"]["type"] == "speed"
