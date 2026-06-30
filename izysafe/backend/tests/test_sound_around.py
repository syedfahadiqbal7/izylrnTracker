"""Tests for Sound Around (F11) — Sprint 5 Slice 1.

Covers the gate stack (can_call → Basic+ tier → watch online → daily quota), the Traccar
command dispatch, the audit-log row, and the quota's interaction with dispatch failures.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core import redis_keys as rk
from app.core.security import create_access_token
from app.models.child import Child, FamilyMember
from app.models.comms import AudioSession
from app.models.device import Device
from app.models.user import User

CHILDREN = "/api/v1/children"


async def _setup(db, redis, *, tier="basic", online=True, with_watch=True, traccar_id=42):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91",
        subscription_tier=tier, timezone="Asia/Kolkata",
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
    device = None
    if with_watch:
        device = Device(
            child_id=child.id, name="Aryan's Watch", device_type="watch",
            imei=uuid.uuid4().hex[:15], traccar_id=traccar_id, protocol="gt06",
        )
        db.add(device)
    await db.flush()
    if device is not None and online and traccar_id is not None:
        await redis.set(rk.device_online(device.id), "1")
    headers = {"Authorization": f"Bearer {create_access_token(str(parent.id))}"}
    return child, parent, device, headers


async def _add_member(db, child_id, *, can_call=False):
    g = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91")
    db.add(g)
    await db.flush()
    db.add(FamilyMember(
        child_id=child_id, user_id=g.id, role="guardian",
        is_primary=False, can_view=True, can_call=can_call, can_manage=False,
    ))
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(str(g.id))}"}


def _url(child_id) -> str:
    return f"{CHILDREN}/{child_id}/sound-around"


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
async def test_start_success(client, db_session, redis_client, fake_traccar_gateway):
    child, parent, device, headers = await _setup(db_session, redis_client)
    resp = await client.post(_url(child.id), headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["child_id"] == str(child.id)
    assert data["device_id"] == str(device.id)
    assert data["user_id"] == str(parent.id)
    assert data["duration_s"] is None
    # Traccar command dispatched to the watch, dialing the requesting parent's phone.
    assert fake_traccar_gateway.sound_around_calls == [(42, parent.phone)]
    # Audit-log row written.
    count = (await db_session.execute(
        select(func.count()).select_from(AudioSession).where(AudioSession.child_id == child.id)
    )).scalar_one()
    assert count == 1
    # Quota consumed.
    assert await redis_client.get(rk.sound_sessions(child.id)) == "1"


# --------------------------------------------------------------------------- #
# Authorization gates
# --------------------------------------------------------------------------- #
async def test_non_member_404(client, db_session, redis_client):
    child, _, _, _ = await _setup(db_session, redis_client)
    stranger = User(phone="+919822222222", country_code="+91")
    db_session.add(stranger)
    await db_session.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(stranger.id))}"}
    resp = await client.post(_url(child.id), headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_FOUND"


async def test_member_without_can_call_403(client, db_session, redis_client):
    child, _, _, _ = await _setup(db_session, redis_client)
    g_headers = await _add_member(db_session, child.id, can_call=False)
    resp = await client.post(_url(child.id), headers=g_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# --------------------------------------------------------------------------- #
# Tier gate (Basic+, over the primary parent)
# --------------------------------------------------------------------------- #
async def test_free_tier_blocked(client, db_session, redis_client, fake_traccar_gateway):
    child, _, _, headers = await _setup(db_session, redis_client, tier="free")
    resp = await client.post(_url(child.id), headers=headers)
    assert resp.status_code == 402
    assert resp.json()["code"] == "SOUND_AROUND_REQUIRES_BASIC"
    assert fake_traccar_gateway.calls == []  # no command dispatched


async def test_premium_tier_allowed(client, db_session, redis_client):
    child, _, _, headers = await _setup(db_session, redis_client, tier="premium")
    resp = await client.post(_url(child.id), headers=headers)
    assert resp.status_code == 201


# --------------------------------------------------------------------------- #
# Watch-online gate
# --------------------------------------------------------------------------- #
async def test_no_watch_404(client, db_session, redis_client):
    child, _, _, headers = await _setup(db_session, redis_client, with_watch=False)
    resp = await client.post(_url(child.id), headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_WATCH"


async def test_watch_offline_409(client, db_session, redis_client):
    child, _, _, headers = await _setup(db_session, redis_client, online=False)
    resp = await client.post(_url(child.id), headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "WATCH_OFFLINE"


async def test_watch_without_traccar_id_treated_offline(client, db_session, redis_client):
    # A watch with no Traccar id isn't commandable → 409 (not a 500).
    child, _, _, headers = await _setup(db_session, redis_client, traccar_id=None)
    resp = await client.post(_url(child.id), headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "WATCH_OFFLINE"


# --------------------------------------------------------------------------- #
# Daily quota
# --------------------------------------------------------------------------- #
async def test_daily_limit_reached(client, db_session, redis_client):
    child, _, _, headers = await _setup(db_session, redis_client)
    for _ in range(3):
        assert (await client.post(_url(child.id), headers=headers)).status_code == 201
    resp = await client.post(_url(child.id), headers=headers)
    assert resp.status_code == 429
    assert resp.json()["code"] == "SOUND_AROUND_LIMIT_REACHED"


async def test_quota_has_midnight_ttl(client, db_session, redis_client):
    child, _, _, headers = await _setup(db_session, redis_client)
    await client.post(_url(child.id), headers=headers)
    ttl = await redis_client.ttl(rk.sound_sessions(child.id))
    assert 0 < ttl <= 86_400  # expires by the next midnight, never persists forever


# --------------------------------------------------------------------------- #
# Dispatch failure
# --------------------------------------------------------------------------- #
async def test_dispatch_failure_502_does_not_consume_quota_or_log(
    client, db_session, redis_client, fake_traccar_gateway
):
    fake_traccar_gateway.ok = False  # Traccar rejects / unreachable
    child, _, _, headers = await _setup(db_session, redis_client)
    resp = await client.post(_url(child.id), headers=headers)
    assert resp.status_code == 502
    assert resp.json()["code"] == "SOUND_AROUND_DISPATCH_FAILED"
    # Neither the quota nor the audit log advanced on a failed dispatch.
    assert await redis_client.get(rk.sound_sessions(child.id)) is None
    count = (await db_session.execute(
        select(func.count()).select_from(AudioSession).where(AudioSession.child_id == child.id)
    )).scalar_one()
    assert count == 0
