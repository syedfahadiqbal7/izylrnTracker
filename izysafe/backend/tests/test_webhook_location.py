"""Tests for the Traccar position webhook hot path (Sprint 2, Slice 1).

Covers: secret auth, device resolution (traccar_id + IMEI fallback + cache),
coord/validity checks, unit conversion, and the three Redis writes (latest cache,
online TTL, batch buffer).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core import redis_keys as rk
from app.core.config import settings
from app.models.child import Child
from app.models.device import Device

URL = "/api/v1/webhook/traccar"
SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #
async def _make_device(db, *, traccar_id=7, imei="863844051234567"):
    child = Child(name="Aryan")
    db.add(child)
    await db.flush()
    device = Device(
        child_id=child.id,
        name="Aryan Watch",
        device_type="watch",
        imei=imei,
        traccar_id=traccar_id,
        protocol="gt06",
    )
    db.add(device)
    await db.flush()
    return child, device


def _payload(*, traccar_id=7, imei="863844051234567", lat=25.2048, lng=55.2708,
             speed=10.0, battery=80, valid=True, ts=None, motion=True):
    ts = ts or datetime.now(timezone.utc)
    return {
        "position": {
            "deviceId": traccar_id,
            "protocol": "gt06",
            "latitude": lat,
            "longitude": lng,
            "altitude": 12.0,
            "speed": speed,            # knots
            "course": 90.0,
            "accuracy": 8.0,
            "valid": valid,
            "fixTime": ts.isoformat(),
            "attributes": {"batteryLevel": battery, "motion": motion},
        },
        "device": {"id": traccar_id, "uniqueId": imei, "status": "online"},
    }


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
async def test_missing_secret_rejected(client, db_session):
    await _make_device(db_session)
    resp = await client.post(URL, json=_payload())
    assert resp.status_code == 401
    assert resp.json()["code"] == "WEBHOOK_UNAUTHORIZED"


async def test_wrong_secret_rejected(client, db_session):
    await _make_device(db_session)
    resp = await client.post(URL, headers={"X-Traccar-Secret": "nope"}, json=_payload())
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Happy path + Redis writes
# --------------------------------------------------------------------------- #
async def test_accepts_and_writes_all_three_redis_keys(client, db_session, redis_client):
    child, device = await _make_device(db_session)
    resp = await client.post(URL, headers=SECRET_HEADERS, json=_payload(battery=80, speed=10.0))
    assert resp.status_code == 200
    assert resp.json() == {"status": "accepted", "stale": False}

    # child latest cache
    raw = await redis_client.get(rk.loc_child_latest(child.id))
    cached = json.loads(raw)
    assert cached["lat"] == 25.2048 and cached["lng"] == 55.2708
    assert cached["battery"] == 80
    assert cached["device_id"] == str(device.id)
    assert cached["speed"] == pytest.approx(18.5, abs=0.05)  # 10 kn → 18.52 km/h

    # device latest cache
    assert await redis_client.get(rk.loc_device_latest(device.id)) is not None

    # online TTL (5 min sliding)
    assert await redis_client.get(rk.device_online(device.id)) == "1"
    ttl = await redis_client.ttl(rk.device_online(device.id))
    assert 0 < ttl <= rk.ONLINE_TTL

    # batch buffer holds one row with the converted speed + denormalized child_id
    rows = await redis_client.lrange(rk.BATCH_LOCATIONS, 0, -1)
    assert len(rows) == 1
    row = json.loads(rows[0])
    assert row["child_id"] == str(child.id)
    assert row["device_id"] == str(device.id)
    assert row["speed"] == pytest.approx(18.5, abs=0.05)
    assert row["battery"] == 80


async def test_resolution_cached_in_redis(client, db_session, redis_client):
    _, device = await _make_device(db_session, traccar_id=42)
    await client.post(URL, headers=SECRET_HEADERS, json=_payload(traccar_id=42))
    cached = await redis_client.get(rk.traccar_device_map(42))
    assert cached is not None
    data = json.loads(cached)
    assert data["device_id"] == str(device.id)


async def test_imei_fallback_when_traccar_id_unset(client, db_session, redis_client):
    # Device paired but traccar_id not yet stored → resolve by IMEI (uniqueId).
    child = Child(name="Zoya")
    db_session.add(child)
    await db_session.flush()
    device = Device(
        child_id=child.id, name="Zoya Watch", device_type="watch",
        imei="111122223333444", traccar_id=None, protocol="gt06",
    )
    db_session.add(device)
    await db_session.flush()

    resp = await client.post(
        URL, headers=SECRET_HEADERS,
        json=_payload(traccar_id=999, imei="111122223333444"),
    )
    assert resp.json()["status"] == "accepted"
    assert await redis_client.get(rk.loc_child_latest(child.id)) is not None


# --------------------------------------------------------------------------- #
# Drop conditions (always ack 200)
# --------------------------------------------------------------------------- #
async def test_unknown_device_ignored(client, db_session, redis_client):
    await _make_device(db_session, traccar_id=7)
    resp = await client.post(
        URL, headers=SECRET_HEADERS, json=_payload(traccar_id=8888, imei="000000000000000")
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored", "reason": "unknown_device"}
    assert await redis_client.llen(rk.BATCH_LOCATIONS) == 0


@pytest.mark.parametrize(
    "lat,lng",
    [(0.0, 0.0), (91.0, 10.0), (10.0, 200.0)],
)
async def test_invalid_coordinates_ignored(client, db_session, redis_client, lat, lng):
    child, _ = await _make_device(db_session)
    resp = await client.post(URL, headers=SECRET_HEADERS, json=_payload(lat=lat, lng=lng))
    assert resp.status_code == 200
    assert resp.json()["reason"] == "invalid_coordinates"
    assert await redis_client.get(rk.loc_child_latest(child.id)) is None


async def test_invalid_flag_ignored(client, db_session, redis_client):
    child, _ = await _make_device(db_session)
    resp = await client.post(URL, headers=SECRET_HEADERS, json=_payload(valid=False))
    assert resp.json()["reason"] == "invalid_coordinates"
    assert await redis_client.llen(rk.BATCH_LOCATIONS) == 0


# --------------------------------------------------------------------------- #
# Staleness — stored, but flagged (alert suppression lands in later slices)
# --------------------------------------------------------------------------- #
async def test_stale_position_stored_and_flagged(client, db_session, redis_client):
    child, _ = await _make_device(db_session)
    old_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    resp = await client.post(URL, headers=SECRET_HEADERS, json=_payload(ts=old_ts))
    assert resp.status_code == 200
    assert resp.json() == {"status": "accepted", "stale": True}
    # still cached + buffered despite being stale
    assert await redis_client.get(rk.loc_child_latest(child.id)) is not None
    assert await redis_client.llen(rk.BATCH_LOCATIONS) == 1


async def test_missing_battery_is_none(client, db_session, redis_client):
    child, _ = await _make_device(db_session)
    payload = _payload()
    del payload["position"]["attributes"]["batteryLevel"]
    await client.post(URL, headers=SECRET_HEADERS, json=payload)
    cached = json.loads(await redis_client.get(rk.loc_child_latest(child.id)))
    assert cached["battery"] is None


# --------------------------------------------------------------------------- #
# Firebase live-location write (off the hot path, via BackgroundTask)
# --------------------------------------------------------------------------- #
async def test_live_location_written_on_accept(client, db_session, fake_realtime_gateway):
    child, device = await _make_device(db_session)
    await client.post(URL, headers=SECRET_HEADERS, json=_payload(battery=80, speed=10.0))

    assert len(fake_realtime_gateway.calls) == 1
    child_id, payload = fake_realtime_gateway.calls[0]
    assert child_id == str(child.id)
    assert payload["lat"] == 25.2048 and payload["lng"] == 55.2708
    assert payload["battery"] == 80
    assert payload["device_id"] == str(device.id)
    assert payload["speed"] == pytest.approx(18.5, abs=0.05)


async def test_live_location_payload_matches_cache(client, db_session, redis_client, fake_realtime_gateway):
    child, _ = await _make_device(db_session)
    await client.post(URL, headers=SECRET_HEADERS, json=_payload())
    cached = json.loads(await redis_client.get(rk.loc_child_latest(child.id)))
    _, live = fake_realtime_gateway.calls[0]
    assert live == cached  # Firebase live write is the same payload as the child cache


@pytest.mark.parametrize(
    "kwargs", [{"traccar_id": 8888, "imei": "x"}, {"lat": 0.0, "lng": 0.0}, {"valid": False}]
)
async def test_no_live_write_when_ignored(client, db_session, fake_realtime_gateway, kwargs):
    await _make_device(db_session)
    await client.post(URL, headers=SECRET_HEADERS, json=_payload(**kwargs))
    assert fake_realtime_gateway.calls == []
