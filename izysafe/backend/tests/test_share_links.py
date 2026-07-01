"""Tests for Share Links + latest-location (Sprint 7 Slice 3, F22).

Covers create (TTL options + Basic+ gate + authz), list, revoke, the PUBLIC
`GET /share/{token}` (name + live location only, view-count bump, revoked/expired/
unknown → 404, IP rate limit), and the authed `GET /children/{id}/location/latest`.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core import redis_keys as rk
from app.core.security import create_access_token
from app.models.child import Child, FamilyMember
from app.models.route import ShareLink
from app.models.user import User

CHILDREN = "/api/v1/children"
SHARE_LINKS = "/api/v1/share-links"
SHARE = "/api/v1/share"


async def _setup(db, *, tier="basic", name="Aryan Kumar"):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91", subscription_tier=tier,
    )
    db.add(parent)
    await db.flush()
    child = Child(name=name)
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(parent.id))}"}
    return child, parent, headers


async def _add_member(db, child_id, *, can_view=True, can_manage=False):
    g = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91")
    db.add(g)
    await db.flush()
    db.add(FamilyMember(
        child_id=child_id, user_id=g.id, role="guardian",
        is_primary=False, can_view=can_view, can_call=False, can_manage=can_manage,
    ))
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(str(g.id))}"}


async def _create(client, child_id, headers, payload=None):
    return await client.post(
        f"{CHILDREN}/{child_id}/share-links", headers=headers, json=payload or {}
    )


async def _seed_fix(redis, child_id, lat=18.52, lng=73.85, ts="2026-06-17T12:00:00+00:00"):
    await redis.set(
        rk.loc_child_latest(child_id),
        json.dumps({"lat": lat, "lng": lng, "device_id": "d", "battery": 80, "ts": ts}),
    )


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
async def test_create_default_ttl(client, db_session):
    child, _, headers = await _setup(db_session)
    resp = await _create(client, child.id, headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert len(data["token"]) == 64
    assert data["token"] in data["url"]
    assert data["view_count"] == 0
    assert data["revoked"] is False
    # ~1 hour default
    exp = datetime.fromisoformat(data["expires_at"])
    delta = exp - datetime.now(timezone.utc)
    assert timedelta(minutes=55) < delta <= timedelta(hours=1, minutes=1)


async def test_create_ttl_options(client, db_session):
    child, _, headers = await _setup(db_session)
    for hours in (1, 8, 24):
        resp = await _create(client, child.id, headers, {"ttl_hours": hours})
        assert resp.status_code == 201, resp.text
        exp = datetime.fromisoformat(resp.json()["data"]["expires_at"])
        assert abs((exp - datetime.now(timezone.utc)).total_seconds() - hours * 3600) < 120


async def test_create_invalid_ttl_rejected(client, db_session):
    child, _, headers = await _setup(db_session)
    for bad in (0, 2, 12, 48):
        resp = await _create(client, child.id, headers, {"ttl_hours": bad})
        assert resp.status_code == 422, bad


async def test_create_free_tier_blocked(client, db_session):
    child, _, headers = await _setup(db_session, tier="free")
    resp = await _create(client, child.id, headers)
    assert resp.status_code == 402
    assert resp.json()["code"] == "SHARE_LINK_REQUIRES_BASIC"


async def test_create_premium_allowed(client, db_session):
    child, _, headers = await _setup(db_session, tier="premium")
    assert (await _create(client, child.id, headers)).status_code == 201


async def test_create_requires_manage(client, db_session):
    child, _, _ = await _setup(db_session)
    guardian = await _add_member(db_session, child.id, can_manage=False)
    resp = await _create(client, child.id, guardian)
    assert resp.status_code == 403


async def test_create_non_member_404(client, db_session, auth_headers):
    child, _, _ = await _setup(db_session)
    resp = await _create(client, child.id, auth_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# List / revoke
# --------------------------------------------------------------------------- #
async def test_list(client, db_session):
    child, _, headers = await _setup(db_session)
    await _create(client, child.id, headers)
    await _create(client, child.id, headers, {"ttl_hours": 8})
    resp = await client.get(f"{CHILDREN}/{child.id}/share-links", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


async def test_revoke(client, db_session):
    child, _, headers = await _setup(db_session)
    link_id = (await _create(client, child.id, headers)).json()["data"]["id"]
    resp = await client.delete(f"{SHARE_LINKS}/{link_id}", headers=headers)
    assert resp.status_code == 200

    link = (
        await db_session.execute(select(ShareLink).where(ShareLink.id == uuid.UUID(link_id)))
    ).scalar_one()
    assert link.revoked is True


async def test_revoke_requires_manage(client, db_session):
    child, _, headers = await _setup(db_session)
    link_id = (await _create(client, child.id, headers)).json()["data"]["id"]
    guardian = await _add_member(db_session, child.id, can_manage=False)
    resp = await client.delete(f"{SHARE_LINKS}/{link_id}", headers=guardian)
    assert resp.status_code == 403


async def test_revoke_non_member_404(client, db_session, auth_headers):
    child, _, headers = await _setup(db_session)
    link_id = (await _create(client, child.id, headers)).json()["data"]["id"]
    resp = await client.delete(f"{SHARE_LINKS}/{link_id}", headers=auth_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Public GET /share/{token}
# --------------------------------------------------------------------------- #
async def test_public_valid_with_location(client, db_session, redis_client):
    child, _, headers = await _setup(db_session, name="Aryan Kumar")
    token = (await _create(client, child.id, headers)).json()["data"]["token"]
    await _seed_fix(redis_client, child.id, lat=18.52, lng=73.85)

    resp = await client.get(f"{SHARE}/{token}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["child_name"] == "Aryan"  # first name only (D10)
    assert data["location"]["lat"] == 18.52
    assert data["location"]["lng"] == 73.85
    # no battery/device leaked
    assert "battery" not in data["location"]


async def test_public_no_fix_returns_null_location(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    token = (await _create(client, child.id, headers)).json()["data"]["token"]
    resp = await client.get(f"{SHARE}/{token}")
    assert resp.status_code == 200
    assert resp.json()["data"]["location"] is None


async def test_public_bumps_view_count(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    link_id = (await _create(client, child.id, headers)).json()["data"]["id"]
    token = (
        await db_session.execute(select(ShareLink).where(ShareLink.id == uuid.UUID(link_id)))
    ).scalar_one().token

    await client.get(f"{SHARE}/{token}")
    await client.get(f"{SHARE}/{token}")

    link = (
        await db_session.execute(select(ShareLink).where(ShareLink.id == uuid.UUID(link_id)))
    ).scalar_one()
    await db_session.refresh(link)
    assert link.view_count == 2


async def test_public_revoked_404(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    created = (await _create(client, child.id, headers)).json()["data"]
    await client.delete(f"{SHARE_LINKS}/{created['id']}", headers=headers)
    resp = await client.get(f"{SHARE}/{created['token']}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "SHARE_LINK_NOT_FOUND"


async def test_public_expired_404(client, db_session, redis_client):
    child, _, _ = await _setup(db_session)
    link = ShareLink(
        child_id=child.id, token="e" * 64,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(link)
    await db_session.flush()
    resp = await client.get(f"{SHARE}/{'e' * 64}")
    assert resp.status_code == 404


async def test_public_unknown_token_404(client, db_session, redis_client):
    resp = await client.get(f"{SHARE}/{'0' * 64}")
    assert resp.status_code == 404


async def test_public_rate_limited(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    token = (await _create(client, child.id, headers)).json()["data"]["token"]
    # Pre-seed the per-IP counter at the limit; the next view trips 429.
    await redis_client.set(rk.share_view_rate("127.0.0.1"), 60)
    resp = await client.get(f"{SHARE}/{token}")
    assert resp.status_code == 429
    assert resp.json()["code"] == "RATE_LIMIT_SHARE"


# --------------------------------------------------------------------------- #
# Authed latest-location
# --------------------------------------------------------------------------- #
async def test_latest_location(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    await _seed_fix(redis_client, child.id, lat=18.52, lng=73.85)
    resp = await client.get(f"{CHILDREN}/{child.id}/location/latest", headers=headers)
    assert resp.status_code == 200, resp.text
    loc = resp.json()["data"]["location"]
    assert loc["lat"] == 18.52 and loc["lng"] == 73.85
    assert loc["timestamp"] is not None


async def test_latest_location_none(client, db_session, redis_client):
    child, _, headers = await _setup(db_session)
    resp = await client.get(f"{CHILDREN}/{child.id}/location/latest", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["location"] is None


async def test_latest_location_non_member_404(client, db_session, auth_headers):
    child, _, _ = await _setup(db_session)
    resp = await client.get(f"{CHILDREN}/{child.id}/location/latest", headers=auth_headers)
    assert resp.status_code == 404
