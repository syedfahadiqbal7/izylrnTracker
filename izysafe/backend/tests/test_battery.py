"""Tests for battery alerts (Sprint 2, Slice 5).

Covers level thresholds, debounce, low→critical escalation, recharge reset,
last_battery persistence, and the webhook wiring.
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
from app.services.battery_service import BatteryService
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway

SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _device(db, *, threshold=20, last_battery=None, traccar_id=None):
    child = Child(name="Aryan")
    db.add(child)
    await db.flush()
    dev = Device(
        child_id=child.id, name="Aryan Watch", device_type="watch",
        imei=uuid.uuid4().hex[:15], battery_threshold=threshold,
        last_battery=last_battery, traccar_id=traccar_id,
    )
    db.add(dev)
    await db.flush()
    return child, dev


async def _member(db, child_id, fcm="parent-tok"):
    u = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91", fcm_token=fcm)
    db.add(u)
    await db.flush()
    db.add(FamilyMember(
        child_id=child_id, user_id=u.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    await db.flush()
    return u


def _svc(db_session, redis, fcm):
    return BatteryService(lambda: NonClosingSession(db_session), redis, fcm)


async def _alerts(db, child_id, alert_type=None):
    stmt = select(func.count()).select_from(Alert).where(Alert.child_id == child_id)
    if alert_type:
        stmt = stmt.where(Alert.type == alert_type)
    return (await db.execute(stmt)).scalar_one()


# --------------------------------------------------------------------------- #
# Levels
# --------------------------------------------------------------------------- #
async def test_low_battery_fires_alert(db_session, redis_client):
    child, dev = await _device(db_session, threshold=20)
    await _member(db_session, child.id)
    fcm = FakeFcmGateway()

    await _svc(db_session, redis_client, fcm).evaluate(dev.id, 15)

    assert await _alerts(db_session, child.id, "low_battery") == 1
    assert fcm.calls[0]["data"]["type"] == "low_battery"
    assert fcm.calls[0]["tokens"] == ["parent-tok"]
    await db_session.refresh(dev)
    assert dev.last_battery == 15
    assert await redis_client.get(rk.battery_alerted(dev.id)) == "low"


async def test_critical_battery_fires_alert(db_session, redis_client):
    child, dev = await _device(db_session, threshold=20)
    await _member(db_session, child.id)
    fcm = FakeFcmGateway()

    await _svc(db_session, redis_client, fcm).evaluate(dev.id, 4)

    assert await _alerts(db_session, child.id, "critical_battery") == 1
    assert await redis_client.get(rk.battery_alerted(dev.id)) == "critical"


async def test_healthy_battery_no_alert_but_persists(db_session, redis_client):
    child, dev = await _device(db_session, threshold=20, last_battery=90)
    await _member(db_session, child.id)
    fcm = FakeFcmGateway()

    await _svc(db_session, redis_client, fcm).evaluate(dev.id, 80)

    assert fcm.calls == []
    assert await _alerts(db_session, child.id) == 0
    await db_session.refresh(dev)
    assert dev.last_battery == 80                       # still persisted (changed)
    assert await redis_client.get(rk.battery_alerted(dev.id)) is None


async def test_threshold_boundary_is_inclusive(db_session, redis_client):
    child, dev = await _device(db_session, threshold=20)
    await _member(db_session, child.id)
    await _svc(db_session, redis_client, FakeFcmGateway()).evaluate(dev.id, 20)  # == threshold
    assert await _alerts(db_session, child.id, "low_battery") == 1


# --------------------------------------------------------------------------- #
# Debounce / escalation / reset
# --------------------------------------------------------------------------- #
async def test_low_battery_debounced(db_session, redis_client):
    child, dev = await _device(db_session, threshold=20)
    await _member(db_session, child.id)
    svc = _svc(db_session, redis_client, FakeFcmGateway())

    await svc.evaluate(dev.id, 15)
    await svc.evaluate(dev.id, 14)   # still low, within 4h window → no second alert

    assert await _alerts(db_session, child.id, "low_battery") == 1


async def test_low_then_critical_escalates(db_session, redis_client):
    child, dev = await _device(db_session, threshold=20)
    await _member(db_session, child.id)
    svc = _svc(db_session, redis_client, FakeFcmGateway())

    await svc.evaluate(dev.id, 18)   # low
    await svc.evaluate(dev.id, 3)    # critical — escalates despite low debounce

    assert await _alerts(db_session, child.id, "low_battery") == 1
    assert await _alerts(db_session, child.id, "critical_battery") == 1
    assert await redis_client.get(rk.battery_alerted(dev.id)) == "critical"


async def test_recharge_resets_debounce(db_session, redis_client):
    child, dev = await _device(db_session, threshold=20)
    await _member(db_session, child.id)
    svc = _svc(db_session, redis_client, FakeFcmGateway())

    await svc.evaluate(dev.id, 15)   # low → debounce set
    await svc.evaluate(dev.id, 90)   # recharged → debounce cleared
    assert await redis_client.get(rk.battery_alerted(dev.id)) is None
    await svc.evaluate(dev.id, 15)   # low again → fires fresh

    assert await _alerts(db_session, child.id, "low_battery") == 2


# --------------------------------------------------------------------------- #
# Webhook wiring
# --------------------------------------------------------------------------- #
async def test_webhook_triggers_battery_alert(client, db_session, redis_client, fake_fcm_gateway):
    child, dev = await _device(db_session, threshold=20, traccar_id=210)
    await _member(db_session, child.id)
    payload = {
        "position": {
            "deviceId": 210, "latitude": 25.2, "longitude": 55.3,
            "valid": True, "attributes": {"batteryLevel": 10},
        },
        "device": {"id": 210, "uniqueId": dev.imei},
    }
    resp = await client.post("/api/v1/webhook/traccar", headers=SECRET_HEADERS, json=payload)
    assert resp.json()["status"] == "accepted"

    assert await _alerts(db_session, child.id, "low_battery") == 1
    assert fake_fcm_gateway.calls[0]["data"]["type"] == "low_battery"
