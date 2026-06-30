"""Tests for device online/offline status (Sprint 2, Slice 4).

Covers DeviceStatusService.reconcile_online (transition vs. no-op), the
DeviceStatusMonitor offline sweep (flip + alert + dedupe), and the webhook
online-reconcile wiring.
"""
from __future__ import annotations

import time
import uuid

from sqlalchemy import func, select

from app.core import redis_keys as rk
from app.core.config import settings
from app.models.alert import Alert
from app.models.child import Child, FamilyMember
from app.models.device import Device
from app.models.user import User
from app.services.device_status import DeviceStatusMonitor, DeviceStatusService
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway

SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}
THRESHOLD = settings.device_offline_threshold_seconds


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _device(db, *, is_online=True, traccar_id=None, name="Aryan Watch"):
    child = Child(name="Aryan")
    db.add(child)
    await db.flush()
    dev = Device(
        child_id=child.id, name=name, device_type="watch",
        imei=uuid.uuid4().hex[:15], traccar_id=traccar_id, is_online=is_online,
    )
    db.add(dev)
    await db.flush()
    return child, dev


async def _member(db, child_id, *, fcm="tok-1", is_primary=True):
    u = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91", fcm_token=fcm)
    db.add(u)
    await db.flush()
    db.add(FamilyMember(
        child_id=child_id, user_id=u.id, role="parent",
        is_primary=is_primary, can_view=True, can_call=True, can_manage=True,
    ))
    await db.flush()
    return u


def _svc(db_session, redis):
    return DeviceStatusService(lambda: NonClosingSession(db_session), redis)


def _monitor(db_session, redis, fcm):
    return DeviceStatusMonitor(
        redis, lambda: NonClosingSession(db_session), fcm,
        offline_threshold=THRESHOLD, interval=60,
    )


# --------------------------------------------------------------------------- #
# reconcile_online
# --------------------------------------------------------------------------- #
async def test_reconcile_flips_offline_device_online(db_session, redis_client):
    _, dev = await _device(db_session, is_online=False)
    transitioned = await _svc(db_session, redis_client).reconcile_online(dev.id)

    assert transitioned is True
    await db_session.refresh(dev)
    assert dev.is_online is True
    assert dev.last_seen_at is not None
    assert await redis_client.get(rk.device_status(dev.id)) == "online"


async def test_reconcile_noop_when_status_marker_online(db_session, redis_client):
    _, dev = await _device(db_session, is_online=False)
    await redis_client.set(rk.device_status(dev.id), "online")

    transitioned = await _svc(db_session, redis_client).reconcile_online(dev.id)
    assert transitioned is False           # fast path, no DB write
    await db_session.refresh(dev)
    assert dev.is_online is False          # untouched


async def test_reconcile_noop_when_already_online_in_db(db_session, redis_client):
    _, dev = await _device(db_session, is_online=True)  # already online, no marker
    transitioned = await _svc(db_session, redis_client).reconcile_online(dev.id)
    assert transitioned is False           # UPDATE ... WHERE is_online=False matched 0 rows
    assert await redis_client.get(rk.device_status(dev.id)) == "online"


# --------------------------------------------------------------------------- #
# sweep_once
# --------------------------------------------------------------------------- #
async def test_sweep_flips_stale_device_offline_and_alerts(db_session, redis_client):
    child, dev = await _device(db_session, is_online=True)
    await _member(db_session, child.id, fcm="parent-tok")
    await _member(db_session, child.id, fcm=None, is_primary=False)  # guardian, no token
    # last received 20 min ago → past the 15-min threshold
    await redis_client.set(rk.device_lastseen(dev.id), str(time.time() - (THRESHOLD + 300)))

    fcm = FakeFcmGateway()
    flipped = await _monitor(db_session, redis_client, fcm).sweep_once()

    assert flipped == 1
    await db_session.refresh(dev)
    assert dev.is_online is False
    assert await redis_client.get(rk.device_status(dev.id)) == "offline"

    # one inbox alert per family member (2), FCM only to the token-bearing one
    n_alerts = (
        await db_session.execute(
            select(func.count()).select_from(Alert).where(Alert.child_id == child.id)
        )
    ).scalar_one()
    assert n_alerts == 2
    assert len(fcm.calls) == 1
    assert fcm.calls[0]["tokens"] == ["parent-tok"]
    assert fcm.calls[0]["data"]["type"] == "device_offline"


async def test_sweep_ignores_fresh_device(db_session, redis_client):
    child, dev = await _device(db_session, is_online=True)
    await _member(db_session, child.id)
    await redis_client.set(rk.device_lastseen(dev.id), str(time.time() - 60))  # 1 min ago

    flipped = await _monitor(db_session, redis_client, FakeFcmGateway()).sweep_once()
    assert flipped == 0
    await db_session.refresh(dev)
    assert dev.is_online is True


async def test_sweep_flips_device_with_no_lastseen(db_session, redis_client):
    child, dev = await _device(db_session, is_online=True)
    await _member(db_session, child.id)
    # no lastseen key at all → treated as offline

    flipped = await _monitor(db_session, redis_client, FakeFcmGateway()).sweep_once()
    assert flipped == 1
    await db_session.refresh(dev)
    assert dev.is_online is False


async def test_sweep_does_not_realert_offline_device(db_session, redis_client):
    child, dev = await _device(db_session, is_online=False)  # already offline
    await _member(db_session, child.id)

    fcm = FakeFcmGateway()
    flipped = await _monitor(db_session, redis_client, fcm).sweep_once()
    assert flipped == 0          # offline devices aren't candidates → no duplicate alert
    assert fcm.calls == []


# --------------------------------------------------------------------------- #
# Webhook online-reconcile wiring
# --------------------------------------------------------------------------- #
async def test_webhook_marks_device_online(client, db_session, redis_client):
    _, dev = await _device(db_session, is_online=False, traccar_id=321)
    payload = {
        "position": {
            "deviceId": 321, "latitude": 25.2, "longitude": 55.3,
            "valid": True, "attributes": {"batteryLevel": 80},
        },
        "device": {"id": 321, "uniqueId": dev.imei},
    }
    resp = await client.post("/api/v1/webhook/traccar", headers=SECRET_HEADERS, json=payload)
    assert resp.json()["status"] == "accepted"

    await db_session.refresh(dev)
    assert dev.is_online is True                                    # reconcile ran
    assert await redis_client.get(rk.device_lastseen(dev.id)) is not None
    assert await redis_client.get(rk.device_status(dev.id)) == "online"
