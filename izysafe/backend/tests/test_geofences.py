"""Tests for Geofence CRUD: validation, shape rules, tier gating, permissions."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.child import FamilyMember
from app.models.location import Geofence
from app.models.user import User

CHILDREN = "/api/v1/children"
GEOFENCES = "/api/v1/geofences"

CIRCLE = {
    "name": "Home",
    "zone_type": "home",
    "type": "circle",
    "center_lat": 18.5204,
    "center_lng": 73.8567,
    "radius_m": 200,
}
POLYGON = {
    "name": "Backyard",
    "zone_type": "other",
    "type": "polygon",
    "polygon_points": [
        {"lat": 18.50, "lng": 73.80},
        {"lat": 18.60, "lng": 73.80},
        {"lat": 18.60, "lng": 73.90},
    ],
}


async def _make_child(client, headers, name="Aryan") -> str:
    resp = await client.post(CHILDREN, headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create(client, headers, child_id, payload=None):
    return await client.post(
        f"{CHILDREN}/{child_id}/geofences", headers=headers, json=payload or CIRCLE
    )


async def _add_member(db, child_id, *, phone, can_view=True, can_manage=False):
    g = User(phone=phone, country_code="+91")
    db.add(g)
    await db.flush()
    db.add(
        FamilyMember(
            child_id=uuid.UUID(child_id), user_id=g.id, role="guardian",
            is_primary=False, can_view=can_view, can_call=False, can_manage=can_manage,
        )
    )
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(str(g.id))}"}


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
async def test_create_circle(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    resp = await _create(client, auth_headers, cid)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["name"] == "Home"
    assert data["type"] == "circle"
    assert data["radius_m"] == 200
    assert data["child_id"] == cid
    # defaults applied
    assert data["notify_enter"] is True and data["notify_exit"] is True
    assert data["active_days"] == [1, 2, 3, 4, 5]
    assert data["color"] == "#4CAF50"
    assert data["active"] is True


async def test_create_requires_auth(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    resp = await client.post(f"{CHILDREN}/{cid}/geofences", json=CIRCLE)
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_MISSING"


async def test_create_circle_missing_radius_422(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    bad = {"name": "Home", "type": "circle", "center_lat": 18.5, "center_lng": 73.8}
    resp = await _create(client, auth_headers, cid, bad)
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


async def test_create_radius_out_of_range_422(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    bad = {**CIRCLE, "radius_m": 5000}
    resp = await _create(client, auth_headers, cid, bad)
    assert resp.status_code == 422


async def test_create_invalid_color_422(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    bad = {**CIRCLE, "color": "green"}
    resp = await _create(client, auth_headers, cid, bad)
    assert resp.status_code == 422


async def test_create_invalid_active_days_422(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    bad = {**CIRCLE, "active_days": [1, 1, 9]}
    resp = await _create(client, auth_headers, cid, bad)
    assert resp.status_code == 422


async def test_create_half_schedule_422(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    bad = {**CIRCLE, "active_from": "08:00:00"}  # active_to missing
    resp = await _create(client, auth_headers, cid, bad)
    assert resp.status_code == 422


async def test_create_under_unknown_child_404(client, auth_headers):
    resp = await _create(client, auth_headers, str(uuid.uuid4()))
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Polygon shape + tier gate (F19 = Premium+)
# --------------------------------------------------------------------------- #
async def test_polygon_needs_three_points_422(client, auth_headers, user, db_session):
    user.subscription_tier = "premium"
    await db_session.flush()
    cid = await _make_child(client, auth_headers)
    bad = {**POLYGON, "polygon_points": [{"lat": 18.5, "lng": 73.8}, {"lat": 18.6, "lng": 73.8}]}
    resp = await _create(client, auth_headers, cid, bad)
    assert resp.status_code == 422


async def test_polygon_blocked_on_free(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    resp = await _create(client, auth_headers, cid, POLYGON)
    assert resp.status_code == 402
    assert resp.json()["code"] == "POLYGON_REQUIRES_PREMIUM"


async def test_polygon_allowed_on_premium(client, auth_headers, user, db_session):
    user.subscription_tier = "premium"
    await db_session.flush()
    cid = await _make_child(client, auth_headers)
    resp = await _create(client, auth_headers, cid, POLYGON)
    assert resp.status_code == 201
    assert resp.json()["data"]["type"] == "polygon"
    assert len(resp.json()["data"]["polygon_points"]) == 3


# --------------------------------------------------------------------------- #
# List / detail
# --------------------------------------------------------------------------- #
async def test_list_geofences(client, auth_headers, user, db_session):
    user.subscription_tier = "basic"  # free caps at 1 zone
    await db_session.flush()
    cid = await _make_child(client, auth_headers)
    await _create(client, auth_headers, cid, {**CIRCLE, "name": "Home"})
    await _create(client, auth_headers, cid, {**CIRCLE, "name": "School", "zone_type": "school"})
    resp = await client.get(f"{CHILDREN}/{cid}/geofences", headers=auth_headers)
    assert resp.status_code == 200
    names = {g["name"] for g in resp.json()["data"]}
    assert names == {"Home", "School"}


async def test_get_detail(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    gid = (await _create(client, auth_headers, cid)).json()["data"]["id"]
    resp = await client.get(f"{GEOFENCES}/{gid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == gid


async def test_get_unknown_404(client, auth_headers):
    resp = await client.get(f"{GEOFENCES}/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "GEOFENCE_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #
async def test_update_fields(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    gid = (await _create(client, auth_headers, cid)).json()["data"]["id"]
    resp = await client.put(
        f"{GEOFENCES}/{gid}", headers=auth_headers,
        json={"name": "Grandma's", "radius_m": 500, "notify_exit": False},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Grandma's"
    assert data["radius_m"] == 500
    assert data["notify_exit"] is False


async def test_update_invalid_radius_422(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    gid = (await _create(client, auth_headers, cid)).json()["data"]["id"]
    resp = await client.put(f"{GEOFENCES}/{gid}", headers=auth_headers, json={"radius_m": 10})
    assert resp.status_code == 422


async def test_update_to_polygon_without_points_400(client, auth_headers, user, db_session):
    user.subscription_tier = "premium"  # rule out the polygon tier gate
    await db_session.flush()
    cid = await _make_child(client, auth_headers)
    gid = (await _create(client, auth_headers, cid)).json()["data"]["id"]
    resp = await client.put(f"{GEOFENCES}/{gid}", headers=auth_headers, json={"type": "polygon"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_GEOFENCE_SHAPE"


async def test_update_to_polygon_blocked_on_free(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    gid = (await _create(client, auth_headers, cid)).json()["data"]["id"]
    resp = await client.put(
        f"{GEOFENCES}/{gid}", headers=auth_headers,
        json={"type": "polygon", "polygon_points": POLYGON["polygon_points"]},
    )
    assert resp.status_code == 402
    assert resp.json()["code"] == "POLYGON_REQUIRES_PREMIUM"


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #
async def test_delete(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    gid = (await _create(client, auth_headers, cid)).json()["data"]["id"]
    resp = await client.delete(f"{GEOFENCES}/{gid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["success"] is True

    assert (await client.get(f"{GEOFENCES}/{gid}", headers=auth_headers)).status_code == 404
    # hard delete — row is gone
    row = (
        await db_session.execute(select(Geofence).where(Geofence.id == uuid.UUID(gid)))
    ).scalar_one_or_none()
    assert row is None


# --------------------------------------------------------------------------- #
# Tier limits (per child, over the primary parent)
# --------------------------------------------------------------------------- #
async def test_free_tier_one_zone(client, auth_headers):
    cid = await _make_child(client, auth_headers)
    assert (await _create(client, auth_headers, cid, {**CIRCLE, "name": "A"})).status_code == 201
    blocked = await _create(client, auth_headers, cid, {**CIRCLE, "name": "B"})
    assert blocked.status_code == 402
    body = blocked.json()
    assert body["code"] == "GEOFENCE_LIMIT_REACHED"
    assert "Basic" in body["message"]


async def test_basic_tier_five_zones(client, auth_headers, user, db_session):
    user.subscription_tier = "basic"
    await db_session.flush()
    cid = await _make_child(client, auth_headers)
    for i in range(5):
        r = await _create(client, auth_headers, cid, {**CIRCLE, "name": f"Z{i}"})
        assert r.status_code == 201
    blocked = await _create(client, auth_headers, cid, {**CIRCLE, "name": "Z6"})
    assert blocked.status_code == 402
    assert "Premium" in blocked.json()["message"]


async def test_premium_unlimited_zones(client, auth_headers, user, db_session):
    user.subscription_tier = "premium"
    await db_session.flush()
    cid = await _make_child(client, auth_headers)
    for i in range(7):
        r = await _create(client, auth_headers, cid, {**CIRCLE, "name": f"Z{i}"})
        assert r.status_code == 201


# --------------------------------------------------------------------------- #
# Permissions (multi-user)
# --------------------------------------------------------------------------- #
async def test_non_member_cannot_see_geofence(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    gid = (await _create(client, auth_headers, cid)).json()["data"]["id"]
    stranger = User(phone="+919822222222", country_code="+91")
    db_session.add(stranger)
    await db_session.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(stranger.id))}"}
    resp = await client.get(f"{GEOFENCES}/{gid}", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "GEOFENCE_NOT_FOUND"


async def test_guardian_can_view_but_not_manage(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    gid = (await _create(client, auth_headers, cid)).json()["data"]["id"]
    g_headers = await _add_member(
        db_session, cid, phone="+919833333333", can_view=True, can_manage=False
    )
    # can read
    assert (await client.get(f"{GEOFENCES}/{gid}", headers=g_headers)).status_code == 200
    assert (await client.get(f"{CHILDREN}/{cid}/geofences", headers=g_headers)).status_code == 200
    # cannot create / update / delete
    assert (await _create(client, g_headers, cid, {**CIRCLE, "name": "X"})).status_code == 403
    upd = await client.put(f"{GEOFENCES}/{gid}", headers=g_headers, json={"name": "Hacked"})
    assert upd.status_code == 403
    assert (await client.delete(f"{GEOFENCES}/{gid}", headers=g_headers)).status_code == 403
