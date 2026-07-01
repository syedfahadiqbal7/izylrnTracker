"""Tests for Watch Removed detection (Sprint 7 Slice 4, F18).

Covers the alarm-webhook ingest (mark_removed / mark_worn, gated on enabled + Basic+),
the SET-NX episode semantics (duplicate alarms don't reset the timer), the
DeviceStatusMonitor threshold sweep (fire once per episode, per-device threshold,
dedup, stale/disabled cleanup), and the webhook routing (tamper → episode, re-wear →
clear, SOS still works).
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
from app.services.watch_removed_service import WatchRemovedService
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway

SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}
ALARM = "/api/v1/webhook/traccar/alarm"


async def _setup(db, *, tier="basic", enabled=True, threshold=10, fcm="parent-tok", traccar_id=None):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91",
        subscription_tier=tier, fcm_token=fcm,
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
    dev = Device(
        child_id=child.id, name="Aryan Watch", device_type="watch",
        imei=uuid.uuid4().hex[:15], traccar_id=traccar_id,
        watch_removed_enabled=enabled, watch_removed_threshold_min=threshold,
    )
    db.add(dev)
    await db.flush()
    return child, parent, dev


def _svc(db, redis, fcm=None):
    return WatchRemovedService(lambda: NonClosingSession(db), redis, fcm or FakeFcmGateway())


async def _count_alerts(db, child_id):
    return (
        await db.execute(
            select(func.count()).select_from(Alert).where(
                Alert.child_id == child_id, Alert.type == "watch_removed"
            )
        )
    ).scalar_one()


async def _seed_episode(redis, dev_id, *, ago_seconds):
    """Simulate a removal that started `ago_seconds` ago."""
    await redis.set(rk.watch_removed_since(dev_id), time.time() - ago_seconds)
    await redis.sadd(rk.WATCH_REMOVED_PENDING, str(dev_id))


# --------------------------------------------------------------------------- #
# mark_removed
# --------------------------------------------------------------------------- #
async def test_mark_removed_sets_state(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    await _svc(db_session, redis_client).mark_removed(dev.id, child.id)
    assert await redis_client.get(rk.watch_removed_since(dev.id)) is not None
    assert await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))


async def test_mark_removed_disabled_noop(db_session, redis_client):
    child, _, dev = await _setup(db_session, enabled=False)
    await _svc(db_session, redis_client).mark_removed(dev.id, child.id)
    assert await redis_client.get(rk.watch_removed_since(dev.id)) is None
    assert not await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))


async def test_mark_removed_free_tier_noop(db_session, redis_client):
    child, _, dev = await _setup(db_session, tier="free")
    await _svc(db_session, redis_client).mark_removed(dev.id, child.id)
    assert await redis_client.get(rk.watch_removed_since(dev.id)) is None


async def test_mark_removed_nx_does_not_reset(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.mark_removed(dev.id, child.id)
    first = await redis_client.get(rk.watch_removed_since(dev.id))
    await svc.mark_removed(dev.id, child.id)  # duplicate alarm, same episode
    assert await redis_client.get(rk.watch_removed_since(dev.id)) == first


async def test_mark_worn_clears(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    await svc.mark_removed(dev.id, child.id)
    await svc.mark_worn(dev.id)
    assert await redis_client.get(rk.watch_removed_since(dev.id)) is None
    assert not await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))


# --------------------------------------------------------------------------- #
# sweep
# --------------------------------------------------------------------------- #
async def test_sweep_fires_after_threshold(db_session, redis_client):
    child, _, dev = await _setup(db_session, threshold=10)
    fcm = FakeFcmGateway()
    svc = _svc(db_session, redis_client, fcm)
    await _seed_episode(redis_client, dev.id, ago_seconds=11 * 60)  # 11 min > 10 min

    fired = await svc.sweep_once()
    assert fired == 1
    assert await _count_alerts(db_session, child.id) == 1
    assert fcm.calls[-1]["data"]["type"] == "watch_removed"
    assert fcm.calls[-1]["data"]["device_id"] == str(dev.id)
    # episode cleared from pending so it can't re-fire
    assert not await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))


async def test_sweep_not_before_threshold(db_session, redis_client):
    child, _, dev = await _setup(db_session, threshold=10)
    svc = _svc(db_session, redis_client)
    await _seed_episode(redis_client, dev.id, ago_seconds=3 * 60)  # only 3 min
    assert await svc.sweep_once() == 0
    assert await _count_alerts(db_session, child.id) == 0
    assert await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))  # still pending


async def test_sweep_fires_once_then_dedups(db_session, redis_client):
    child, _, dev = await _setup(db_session, threshold=5)
    svc = _svc(db_session, redis_client)
    await _seed_episode(redis_client, dev.id, ago_seconds=6 * 60)
    assert await svc.sweep_once() == 1
    assert await svc.sweep_once() == 0  # already fired + dropped from pending
    assert await _count_alerts(db_session, child.id) == 1


async def test_sweep_respects_per_device_threshold(db_session, redis_client):
    child_a, _, dev_a = await _setup(db_session, threshold=5)
    child_b, _, dev_b = await _setup(db_session, threshold=15)
    svc = _svc(db_session, redis_client)
    await _seed_episode(redis_client, dev_a.id, ago_seconds=6 * 60)   # > 5 → fires
    await _seed_episode(redis_client, dev_b.id, ago_seconds=6 * 60)   # < 15 → not yet

    assert await svc.sweep_once() == 1
    assert await _count_alerts(db_session, child_a.id) == 1
    assert await _count_alerts(db_session, child_b.id) == 0


async def test_sweep_drops_disabled_device(db_session, redis_client):
    child, _, dev = await _setup(db_session, enabled=False, threshold=5)
    svc = _svc(db_session, redis_client)
    await _seed_episode(redis_client, dev.id, ago_seconds=6 * 60)  # in pending, but disabled
    assert await svc.sweep_once() == 0
    assert not await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))


async def test_sweep_drops_stale_without_since(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    await redis_client.sadd(rk.WATCH_REMOVED_PENDING, str(dev.id))  # in set, no since stamp
    assert await _svc(db_session, redis_client).sweep_once() == 0
    assert not await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))


async def test_sweep_empty_noop(db_session, redis_client):
    assert await _svc(db_session, redis_client).sweep_once() == 0


# --------------------------------------------------------------------------- #
# Webhook routing
# --------------------------------------------------------------------------- #
def _alarm(traccar_id, imei, alarm):
    return {
        "position": {
            "deviceId": traccar_id, "latitude": 18.5, "longitude": 73.8,
            "valid": True, "attributes": {"alarm": alarm},
        },
        "device": {"id": traccar_id, "uniqueId": imei},
    }


async def test_webhook_tamper_starts_episode(client, db_session, redis_client):
    child, _, dev = await _setup(db_session, traccar_id=601)
    resp = await client.post(ALARM, headers=SECRET_HEADERS, json=_alarm(601, dev.imei, "tamper"))
    assert resp.status_code == 200
    assert resp.json()["kind"] == "watch_removed"
    assert await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))


async def test_webhook_tamper_disabled_no_episode(client, db_session, redis_client):
    child, _, dev = await _setup(db_session, enabled=False, traccar_id=602)
    resp = await client.post(ALARM, headers=SECRET_HEADERS, json=_alarm(602, dev.imei, "tamper"))
    assert resp.json()["kind"] == "watch_removed"  # webhook accepts; mark is a no-op
    assert not await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))


async def test_webhook_worn_clears_episode(client, db_session, redis_client):
    child, _, dev = await _setup(db_session, traccar_id=603)
    await _seed_episode(redis_client, dev.id, ago_seconds=60)
    resp = await client.post(ALARM, headers=SECRET_HEADERS, json=_alarm(603, dev.imei, "tamperEnd"))
    assert resp.json()["kind"] == "watch_worn"
    assert not await redis_client.sismember(rk.WATCH_REMOVED_PENDING, str(dev.id))
    assert await redis_client.get(rk.watch_removed_since(dev.id)) is None


async def test_webhook_unknown_alarm_ignored(client, db_session):
    child, _, dev = await _setup(db_session, traccar_id=604)
    resp = await client.post(ALARM, headers=SECRET_HEADERS, json=_alarm(604, dev.imei, "geofenceExit"))
    assert resp.json()["reason"] == "not_sos_alarm"
