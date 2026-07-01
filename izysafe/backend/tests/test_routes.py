"""Tests for Safe Route CRUD (Sprint 7 Slice 1, F20) — Premium-gated.

Covers validation (≥2 waypoints, tolerance range, paired schedule window), the
Premium tier gate (free/basic/lapsed blocked), family-member authorization
(manage to write, view to read, 404 for non-members), and update/delete.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.child import Child, FamilyMember
from app.models.route import SafeRoute
from app.models.user import User

CHILDREN = "/api/v1/children"
ROUTES = "/api/v1/routes"

ROUTE = {
    "name": "School run",
    "waypoints": [
        {"lat": 18.5204, "lng": 73.8567, "name": "Home"},
        {"lat": 18.5301, "lng": 73.8650, "name": "School"},
    ],
    "deviation_tolerance_m": 200,
    "active_from": "08:00:00",
    "active_to": "09:00:00",
}


async def _setup(db, *, tier="premium", expires=None):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91",
        subscription_tier=tier, subscription_expires_at=expires,
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


async def _create(client, child_id, headers, payload=ROUTE):
    return await client.post(f"{CHILDREN}/{child_id}/routes", headers=headers, json=payload)


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
async def test_create(client, db_session):
    child, _, headers = await _setup(db_session)
    resp = await _create(client, child.id, headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["name"] == "School run"
    assert len(data["waypoints"]) == 2
    assert data["waypoints"][0]["name"] == "Home"
    assert data["deviation_tolerance_m"] == 200
    assert data["active"] is True


async def test_create_defaults_tolerance_and_days(client, db_session):
    child, _, headers = await _setup(db_session)
    payload = {k: v for k, v in ROUTE.items() if k != "deviation_tolerance_m"}
    resp = await _create(client, child.id, headers, payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["deviation_tolerance_m"] == 200
    assert data["active_days"] == [1, 2, 3, 4, 5]  # weekdays default


# --------------------------------------------------------------------------- #
# Tier gate (Premium)
# --------------------------------------------------------------------------- #
async def test_create_free_tier_blocked(client, db_session):
    child, _, headers = await _setup(db_session, tier="free")
    resp = await _create(client, child.id, headers)
    assert resp.status_code == 402
    assert resp.json()["code"] == "SAFE_ROUTES_REQUIRES_PREMIUM"


async def test_create_basic_tier_blocked(client, db_session):
    child, _, headers = await _setup(db_session, tier="basic")
    resp = await _create(client, child.id, headers)
    assert resp.status_code == 402
    assert resp.json()["code"] == "SAFE_ROUTES_REQUIRES_PREMIUM"


async def test_create_lapsed_premium_blocked(client, db_session):
    # A premium subscription whose expiry has passed is treated as free.
    past = datetime.now(timezone.utc) - timedelta(days=1)
    child, _, headers = await _setup(db_session, tier="premium", expires=past)
    resp = await _create(client, child.id, headers)
    assert resp.status_code == 402
    assert resp.json()["code"] == "SAFE_ROUTES_REQUIRES_PREMIUM"


async def test_create_school_tier_allowed(client, db_session):
    child, _, headers = await _setup(db_session, tier="school")
    resp = await _create(client, child.id, headers)
    assert resp.status_code == 201, resp.text


# --------------------------------------------------------------------------- #
# Validation (→ 422)
# --------------------------------------------------------------------------- #
async def test_create_one_waypoint_rejected(client, db_session):
    child, _, headers = await _setup(db_session)
    payload = {**ROUTE, "waypoints": [{"lat": 18.5, "lng": 73.8}]}
    resp = await _create(client, child.id, headers, payload)
    assert resp.status_code == 422


async def test_create_tolerance_out_of_range_rejected(client, db_session):
    child, _, headers = await _setup(db_session)
    for bad in (50, 501):
        resp = await _create(client, child.id, headers, {**ROUTE, "deviation_tolerance_m": bad})
        assert resp.status_code == 422, bad


async def test_create_missing_schedule_rejected(client, db_session):
    child, _, headers = await _setup(db_session)
    payload = {k: v for k, v in ROUTE.items() if k != "active_from"}
    resp = await _create(client, child.id, headers, payload)
    assert resp.status_code == 422


async def test_create_equal_schedule_bounds_rejected(client, db_session):
    child, _, headers = await _setup(db_session)
    payload = {**ROUTE, "active_from": "08:00:00", "active_to": "08:00:00"}
    resp = await _create(client, child.id, headers, payload)
    assert resp.status_code == 422


async def test_create_bad_active_days_rejected(client, db_session):
    child, _, headers = await _setup(db_session)
    resp = await _create(client, child.id, headers, {**ROUTE, "active_days": [1, 1, 8]})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #
async def test_create_requires_manage(client, db_session):
    child, _, _ = await _setup(db_session)
    guardian = await _add_member(db_session, child.id, can_manage=False)
    resp = await _create(client, child.id, guardian)
    assert resp.status_code == 403


async def test_create_non_member_404(client, db_session, auth_headers):
    # `auth_headers` user has no membership on this child.
    child, _, _ = await _setup(db_session)
    resp = await _create(client, child.id, auth_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------------- #
async def test_list(client, db_session):
    child, _, headers = await _setup(db_session)
    await _create(client, child.id, headers)
    await _create(client, child.id, headers, {**ROUTE, "name": "Park run"})
    resp = await client.get(f"{CHILDREN}/{child.id}/routes", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


async def test_get_by_id(client, db_session):
    child, _, headers = await _setup(db_session)
    rid = (await _create(client, child.id, headers)).json()["data"]["id"]
    resp = await client.get(f"{ROUTES}/{rid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == rid


async def test_get_non_member_404(client, db_session, auth_headers):
    child, _, headers = await _setup(db_session)
    rid = (await _create(client, child.id, headers)).json()["data"]["id"]
    resp = await client.get(f"{ROUTES}/{rid}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "SAFE_ROUTE_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Update / delete
# --------------------------------------------------------------------------- #
async def test_update(client, db_session):
    child, _, headers = await _setup(db_session)
    rid = (await _create(client, child.id, headers)).json()["data"]["id"]
    resp = await client.put(
        f"{ROUTES}/{rid}", headers=headers,
        json={"deviation_tolerance_m": 350, "active": False},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["deviation_tolerance_m"] == 350
    assert data["active"] is False


async def test_update_waypoints(client, db_session):
    child, _, headers = await _setup(db_session)
    rid = (await _create(client, child.id, headers)).json()["data"]["id"]
    new_wps = [
        {"lat": 18.50, "lng": 73.80},
        {"lat": 18.51, "lng": 73.81},
        {"lat": 18.52, "lng": 73.82},
    ]
    resp = await client.put(f"{ROUTES}/{rid}", headers=headers, json={"waypoints": new_wps})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]["waypoints"]) == 3


async def test_update_requires_manage(client, db_session):
    child, _, headers = await _setup(db_session)
    rid = (await _create(client, child.id, headers)).json()["data"]["id"]
    guardian = await _add_member(db_session, child.id, can_manage=False)
    resp = await client.put(f"{ROUTES}/{rid}", headers=guardian, json={"active": False})
    assert resp.status_code == 403


async def test_delete(client, db_session):
    child, _, headers = await _setup(db_session)
    rid = (await _create(client, child.id, headers)).json()["data"]["id"]
    resp = await client.delete(f"{ROUTES}/{rid}", headers=headers)
    assert resp.status_code == 200

    remaining = (
        await db_session.execute(
            select(SafeRoute).where(SafeRoute.id == uuid.UUID(rid))
        )
    ).scalar_one_or_none()
    assert remaining is None


async def test_delete_non_member_404(client, db_session, auth_headers):
    child, _, headers = await _setup(db_session)
    rid = (await _create(client, child.id, headers)).json()["data"]["id"]
    resp = await client.delete(f"{ROUTES}/{rid}", headers=auth_headers)
    assert resp.status_code == 404
