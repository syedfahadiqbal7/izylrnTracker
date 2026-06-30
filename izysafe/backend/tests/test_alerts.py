"""Tests for the Alerts inbox API (Sprint 4 Slice 4).

GET /alerts (pagination + unread/child filters), PUT /alerts/{id}/read,
PUT /alerts/read-all. The inbox is per-user — a user only sees/mutates own rows.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.alert import Alert
from app.models.child import Child
from app.models.user import User

BASE = "/api/v1/alerts"
T0 = datetime(2026, 6, 17, 8, 0, tzinfo=timezone.utc)


async def _alert(db, user_id, *, child_id=None, type="sos", read=False, ts=None, title="t"):
    a = Alert(user_id=user_id, child_id=child_id, type=type, title=title, body="b", read=read)
    if ts is not None:
        a.created_at = ts
    db.add(a)
    await db.flush()
    return a


async def _child(db, name="Kid"):
    c = Child(name=name)
    db.add(c)
    await db.flush()
    return c


# --------------------------------------------------------------------------- #
# List
# --------------------------------------------------------------------------- #
async def test_list_newest_first_with_meta(client, auth_headers, user, db_session):
    await _alert(db_session, user.id, type="sos", ts=T0, title="old")
    await _alert(
        db_session, user.id, type="geofence_enter", ts=T0 + timedelta(hours=1), title="new"
    )
    resp = await client.get(BASE, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert [a["title"] for a in body["data"]] == ["new", "old"]
    assert body["meta"]["total"] == 2
    assert body["meta"]["unread_count"] == 2


async def test_unread_filter(client, auth_headers, user, db_session):
    await _alert(db_session, user.id, read=True)
    await _alert(db_session, user.id, read=False)
    body = (await client.get(f"{BASE}?unread=true", headers=auth_headers)).json()
    assert body["meta"]["total"] == 1
    assert all(a["read"] is False for a in body["data"])


async def test_child_filter(client, auth_headers, user, db_session):
    a = await _child(db_session, "A")
    b = await _child(db_session, "B")
    await _alert(db_session, user.id, child_id=a.id)
    await _alert(db_session, user.id, child_id=b.id)
    await _alert(db_session, user.id, child_id=None)
    body = (await client.get(f"{BASE}?child_id={a.id}", headers=auth_headers)).json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["child_id"] == str(a.id)


async def test_pagination(client, auth_headers, user, db_session):
    for i in range(3):
        await _alert(db_session, user.id, ts=T0 + timedelta(minutes=i))
    p1 = (await client.get(f"{BASE}?page=1&page_size=2", headers=auth_headers)).json()
    p2 = (await client.get(f"{BASE}?page=2&page_size=2", headers=auth_headers)).json()
    assert len(p1["data"]) == 2 and p1["meta"]["total"] == 3
    assert len(p2["data"]) == 1


async def test_only_own_alerts(client, auth_headers, user, db_session):
    other = User(phone="+919800000123", country_code="+91")
    db_session.add(other)
    await db_session.flush()
    await _alert(db_session, user.id, title="mine")
    await _alert(db_session, other.id, title="theirs")
    body = (await client.get(BASE, headers=auth_headers)).json()
    assert [a["title"] for a in body["data"]] == ["mine"]


async def test_list_requires_auth(client):
    assert (await client.get(BASE)).status_code == 401


# --------------------------------------------------------------------------- #
# Mark read
# --------------------------------------------------------------------------- #
async def test_mark_read(client, auth_headers, user, db_session):
    a = await _alert(db_session, user.id, read=False)
    resp = await client.put(f"{BASE}/{a.id}/read", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["read"] is True
    # idempotent
    assert (await client.put(f"{BASE}/{a.id}/read", headers=auth_headers)).status_code == 200
    # no longer in the unread list
    body = (await client.get(f"{BASE}?unread=true", headers=auth_headers)).json()
    assert body["meta"]["total"] == 0


async def test_mark_read_unknown_404(client, auth_headers):
    resp = await client.put(f"{BASE}/{uuid.uuid4()}/read", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "ALERT_NOT_FOUND"


async def test_cannot_mark_others_alert(client, auth_headers, db_session):
    other = User(phone="+919800000124", country_code="+91")
    db_session.add(other)
    await db_session.flush()
    a = await _alert(db_session, other.id)
    resp = await client.put(f"{BASE}/{a.id}/read", headers=auth_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Mark all read
# --------------------------------------------------------------------------- #
async def test_mark_all_read(client, auth_headers, user, db_session):
    for _ in range(3):
        await _alert(db_session, user.id, read=False)
    resp = await client.put(f"{BASE}/read-all", headers=auth_headers)
    assert resp.json()["data"]["updated"] == 3
    body = (await client.get(f"{BASE}?unread=true", headers=auth_headers)).json()
    assert body["meta"]["total"] == 0


async def test_mark_all_read_child_scoped(client, auth_headers, user, db_session):
    a = await _child(db_session, "A")
    b = await _child(db_session, "B")
    await _alert(db_session, user.id, child_id=a.id, read=False)
    await _alert(db_session, user.id, child_id=a.id, read=False)
    await _alert(db_session, user.id, child_id=b.id, read=False)
    resp = await client.put(f"{BASE}/read-all?child_id={a.id}", headers=auth_headers)
    assert resp.json()["data"]["updated"] == 2
    # B's alert is still unread
    body = (await client.get(f"{BASE}?unread=true", headers=auth_headers)).json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["child_id"] == str(b.id)
