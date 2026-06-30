"""Tests for SOS (Flow C) Slice 1 — alarm webhook + SosService.

Covers the trigger fan-out (sos_events row, inbox alerts, urgent FCM, Firebase SOS
node, Redis active marker), dedup (one active per child), location fallback to the
last-known fix, and the webhook wiring (auth, SOS-only filter, unknown device).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core import redis_keys as rk
from app.core.config import settings
from app.models.alert import Alert
from app.models.child import Child, FamilyMember
from app.models.device import Device
from app.models.sos import SosEvent
from app.models.user import User
from app.services.sos_service import SosAlarmService
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway, FakeRealtimeGateway

SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}
LAT, LNG = 18.5204, 73.8567


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _setup(db, *, fcm="parent-tok", traccar_id=401):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91", fcm_token=fcm,
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
        child_id=child.id, name="Watch", device_type="watch",
        imei=uuid.uuid4().hex[:15], traccar_id=traccar_id,
    )
    db.add(dev)
    await db.flush()
    return child, parent, dev


def _svc(db, redis, realtime=None, fcm=None):
    return SosAlarmService(
        lambda: NonClosingSession(db), redis,
        realtime or FakeRealtimeGateway(), fcm or FakeFcmGateway(),
    )


async def _active_count(db, child_id):
    return (
        await db.execute(
            select(func.count()).select_from(SosEvent).where(
                SosEvent.child_id == child_id, SosEvent.status == "active"
            )
        )
    ).scalar_one()


def _alarm(traccar_id, imei, lat=LAT, lng=LNG, alarm="sos", valid=True):
    attrs = {} if alarm is None else {"alarm": alarm}
    return {
        "position": {
            "deviceId": traccar_id, "latitude": lat, "longitude": lng,
            "valid": valid, "attributes": attrs,
        },
        "device": {"id": traccar_id, "uniqueId": imei},
    }


# --------------------------------------------------------------------------- #
# SosAlarmService
# --------------------------------------------------------------------------- #
async def test_trigger_creates_sos_and_fans_out(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    realtime, fcm = FakeRealtimeGateway(), FakeFcmGateway()
    sos_id = await _svc(db_session, redis_client, realtime, fcm).trigger_from_alarm(
        child.id, dev.id, LAT, LNG
    )

    assert sos_id is not None
    sos = (await db_session.execute(select(SosEvent).where(SosEvent.id == sos_id))).scalar_one()
    assert sos.status == "active" and sos.lat == LAT and sos.approximate is False
    # one inbox row for the family member, typed 'sos'
    assert (await db_session.execute(
        select(func.count()).select_from(Alert).where(
            Alert.child_id == child.id, Alert.type == "sos"
        )
    )).scalar_one() == 1
    # urgent multicast push to the parent
    assert fcm.calls[-1]["urgent"] is True
    assert fcm.calls[-1]["data"]["type"] == "sos"
    assert fcm.calls[-1]["tokens"] == ["parent-tok"]
    # Firebase SOS node + Redis active marker
    assert realtime.sos_calls[-1][0] == str(child.id)
    assert realtime.sos_calls[-1][1]["active"] is True
    assert await redis_client.get(rk.sos_active(child.id)) == "1"


async def test_dedup_one_active_per_child(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    svc = _svc(db_session, redis_client)
    first = await svc.trigger_from_alarm(child.id, dev.id, LAT, LNG)
    second = await svc.trigger_from_alarm(child.id, dev.id, LAT, LNG)
    assert first is not None and second is None
    assert await _active_count(db_session, child.id) == 1


async def test_location_falls_back_to_last_known(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    await redis_client.set(
        rk.loc_child_latest(child.id), json.dumps({"lat": LAT, "lng": LNG})
    )
    sos_id = await _svc(db_session, redis_client).trigger_from_alarm(child.id, dev.id, None, None)
    sos = (await db_session.execute(select(SosEvent).where(SosEvent.id == sos_id))).scalar_one()
    assert (sos.lat, sos.lng) == (LAT, LNG)
    assert sos.approximate is True


async def test_no_location_anywhere_is_approximate_null(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    sos_id = await _svc(db_session, redis_client).trigger_from_alarm(child.id, dev.id, None, None)
    sos = (await db_session.execute(select(SosEvent).where(SosEvent.id == sos_id))).scalar_one()
    assert sos.lat is None and sos.lng is None and sos.approximate is True


async def test_null_island_coords_fall_back(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    sos_id = await _svc(db_session, redis_client).trigger_from_alarm(child.id, dev.id, 0.0, 0.0)
    sos = (await db_session.execute(select(SosEvent).where(SosEvent.id == sos_id))).scalar_one()
    assert sos.approximate is True  # (0,0) rejected → fell through


async def test_deleted_child_no_sos(db_session, redis_client):
    child, _, dev = await _setup(db_session)
    child.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()
    sos_id = await _svc(db_session, redis_client).trigger_from_alarm(child.id, dev.id, LAT, LNG)
    assert sos_id is None
    assert await _active_count(db_session, child.id) == 0


# --------------------------------------------------------------------------- #
# Alarm webhook
# --------------------------------------------------------------------------- #
async def test_webhook_alarm_triggers_sos(
    client, db_session, redis_client, fake_fcm_gateway, fake_realtime_gateway
):
    child, _, dev = await _setup(db_session, traccar_id=410)
    resp = await client.post(
        "/api/v1/webhook/traccar/alarm", headers=SECRET_HEADERS,
        json=_alarm(410, dev.imei),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    assert await _active_count(db_session, child.id) == 1
    assert fake_fcm_gateway.calls[-1]["urgent"] is True
    assert fake_fcm_gateway.calls[-1]["data"]["type"] == "sos"
    assert fake_realtime_gateway.sos_calls[-1][1]["active"] is True


async def test_webhook_alarm_requires_secret(client, db_session):
    _, _, dev = await _setup(db_session, traccar_id=411)
    resp = await client.post("/api/v1/webhook/traccar/alarm", json=_alarm(411, dev.imei))
    assert resp.status_code == 401
    assert resp.json()["code"] == "WEBHOOK_UNAUTHORIZED"


async def test_webhook_non_sos_alarm_ignored(client, db_session, fake_fcm_gateway):
    child, _, dev = await _setup(db_session, traccar_id=412)
    resp = await client.post(
        "/api/v1/webhook/traccar/alarm", headers=SECRET_HEADERS,
        json=_alarm(412, dev.imei, alarm="lowBattery"),
    )
    assert resp.json()["reason"] == "not_sos_alarm"
    assert await _active_count(db_session, child.id) == 0


async def test_webhook_unknown_device_ignored(client, db_session):
    resp = await client.post(
        "/api/v1/webhook/traccar/alarm", headers=SECRET_HEADERS,
        json=_alarm(99999, "000000000000000"),
    )
    assert resp.json()["status"] == "ignored"
    assert resp.json()["reason"] == "unknown_device"


async def test_webhook_alarm_deduplicated(client, db_session, redis_client):
    child, _, dev = await _setup(db_session, traccar_id=413)
    payload = _alarm(413, dev.imei)
    await client.post("/api/v1/webhook/traccar/alarm", headers=SECRET_HEADERS, json=payload)
    await client.post("/api/v1/webhook/traccar/alarm", headers=SECRET_HEADERS, json=payload)
    assert await _active_count(db_session, child.id) == 1
