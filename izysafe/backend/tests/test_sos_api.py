"""Tests for the SOS read/resolve API (Sprint 4 Slice 2).

GET /sos/active (family-scoped) and PUT /sos/{id}/resolve (any member; clears the
Firebase active flag + Redis marker; idempotent).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core import redis_keys as rk
from app.core.security import create_access_token
from app.models.child import Child, FamilyMember
from app.models.sos import SosEvent
from app.models.user import User

BASE = "/api/v1/sos"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _setup(db):
    parent = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91", fcm_token="tok")
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
    headers = {"Authorization": f"Bearer {create_access_token(str(parent.id))}"}
    return child, parent, headers


async def _add_member(db, child_id, *, can_manage=False):
    g = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91")
    db.add(g)
    await db.flush()
    db.add(FamilyMember(
        child_id=child_id, user_id=g.id, role="guardian",
        is_primary=False, can_view=True, can_call=False, can_manage=can_manage,
    ))
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(str(g.id))}"}


async def _active_sos(db, redis, child_id):
    sos = SosEvent(
        child_id=child_id, lat=18.5, lng=73.8, status="active",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(sos)
    await db.flush()
    await redis.set(rk.sos_active(child_id), "1")
    return sos


# --------------------------------------------------------------------------- #
# GET /sos/active
# --------------------------------------------------------------------------- #
async def test_list_active(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    sos = await _active_sos(db_session, redis_client, child.id)
    resp = await client.get(f"{BASE}/active", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(sos.id)
    assert data[0]["child_name"] == "Aryan"
    assert data[0]["status"] == "active"


async def test_list_excludes_resolved(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    sos = await _active_sos(db_session, redis_client, child.id)
    sos.status = "resolved"
    await db_session.flush()
    resp = await client.get(f"{BASE}/active", headers=headers)
    assert resp.json()["data"] == []


async def test_list_scoped_to_own_children(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    await _active_sos(db_session, redis_client, child.id)
    # an unrelated family's active SOS
    other_child, _, _ = await _setup(db_session)
    await _active_sos(db_session, redis_client, other_child.id)

    data = (await client.get(f"{BASE}/active", headers=headers)).json()["data"]
    assert {d["child_id"] for d in data} == {str(child.id)}


async def test_list_requires_auth(client):
    resp = await client.get(f"{BASE}/active")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# PUT /sos/{id}/resolve
# --------------------------------------------------------------------------- #
async def test_resolve(client, db_session, redis_client, fake_realtime_gateway):
    child, parent, headers = await _setup(db_session)
    sos = await _active_sos(db_session, redis_client, child.id)

    resp = await client.put(f"{BASE}/{sos.id}/resolve", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "resolved"
    assert data["resolved_by"] == str(parent.id)
    assert data["resolved_at"] is not None

    # Redis marker cleared + Firebase active flag cleared
    assert await redis_client.get(rk.sos_active(child.id)) is None
    assert str(child.id) in fake_realtime_gateway.sos_cleared

    # row persisted as resolved
    row = (await db_session.execute(select(SosEvent).where(SosEvent.id == sos.id))).scalar_one()
    assert row.status == "resolved" and row.resolved_by == parent.id


async def test_resolve_idempotent(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    sos = await _active_sos(db_session, redis_client, child.id)
    first = await client.put(f"{BASE}/{sos.id}/resolve", headers=headers)
    second = await client.put(f"{BASE}/{sos.id}/resolve", headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["data"]["status"] == "resolved"


async def test_resolve_any_member(client, db_session, redis_client):
    # A guardian WITHOUT manage can still resolve (Decision F — it's an emergency).
    child, _, _ = await _setup(db_session)
    sos = await _active_sos(db_session, redis_client, child.id)
    g_headers = await _add_member(db_session, child.id, can_manage=False)
    resp = await client.put(f"{BASE}/{sos.id}/resolve", headers=g_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "resolved"


async def test_resolve_unknown_404(client, db_session, redis_client):
    _, _, headers = await _setup(db_session)
    resp = await client.put(f"{BASE}/{uuid.uuid4()}/resolve", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "SOS_NOT_FOUND"


async def test_resolve_non_member_404(client, db_session, redis_client):
    child, _, _ = await _setup(db_session)
    sos = await _active_sos(db_session, redis_client, child.id)
    stranger = User(phone="+919811111111", country_code="+91")
    db_session.add(stranger)
    await db_session.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(stranger.id))}"}
    resp = await client.put(f"{BASE}/{sos.id}/resolve", headers=headers)
    assert resp.status_code == 404
