"""Tests for Safe Addresses (Sprint 7 Slice 5, F24).

Safe Addresses are not a new table — they're the non-school geofences, surfaced by a
filtered list endpoint, plus best-effort reverse-geocoding to auto-label a zone on
create. Covers the filter (school excluded), authorization, and the geocoding hook
(fills address when omitted, respects an explicit address, circle-only, null-safe).
"""
from __future__ import annotations

import uuid

from app.core.security import create_access_token
from app.models.child import Child, FamilyMember
from app.models.user import User
from app.services.geofence_service import GeofenceService
from tests.fakes import FakeGeocodingGateway

CHILDREN = "/api/v1/children"

CIRCLE = {
    "name": "Home", "zone_type": "home", "type": "circle",
    "center_lat": 18.5204, "center_lng": 73.8567, "radius_m": 200,
}
FAKE_ADDR = "12 MG Road, Pune, India"  # FakeGeocodingGateway default


async def _setup(db, *, tier="premium"):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91", subscription_tier=tier,
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


async def _create(client, child_id, headers, payload):
    return await client.post(f"{CHILDREN}/{child_id}/geofences", headers=headers, json=payload)


# --------------------------------------------------------------------------- #
# Filtered list
# --------------------------------------------------------------------------- #
async def test_safe_addresses_excludes_school(client, db_session):
    child, _, headers = await _setup(db_session)
    await _create(client, child.id, headers, {**CIRCLE, "name": "Home", "zone_type": "home"})
    await _create(client, child.id, headers, {**CIRCLE, "name": "School", "zone_type": "school"})
    await _create(client, child.id, headers, {**CIRCLE, "name": "Grandma", "zone_type": "grandparents"})

    resp = await client.get(f"{CHILDREN}/{child.id}/safe-addresses", headers=headers)
    assert resp.status_code == 200, resp.text
    names = {g["name"] for g in resp.json()["data"]}
    assert names == {"Home", "Grandma"}  # school excluded


async def test_safe_addresses_empty(client, db_session):
    child, _, headers = await _setup(db_session)
    await _create(client, child.id, headers, {**CIRCLE, "zone_type": "school"})
    resp = await client.get(f"{CHILDREN}/{child.id}/safe-addresses", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_safe_addresses_non_member_404(client, db_session, auth_headers):
    child, _, _ = await _setup(db_session)
    resp = await client.get(f"{CHILDREN}/{child.id}/safe-addresses", headers=auth_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Reverse-geocoding on create
# --------------------------------------------------------------------------- #
async def test_create_reverse_geocodes_when_address_omitted(
    client, db_session, fake_geocoding_gateway
):
    child, _, headers = await _setup(db_session)
    resp = await _create(client, child.id, headers, CIRCLE)  # no address
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["address"] == FAKE_ADDR
    assert fake_geocoding_gateway.calls == [(18.5204, 73.8567)]


async def test_create_keeps_explicit_address(client, db_session, fake_geocoding_gateway):
    child, _, headers = await _setup(db_session)
    resp = await _create(client, child.id, headers, {**CIRCLE, "address": "My Own Label"})
    assert resp.status_code == 201
    assert resp.json()["data"]["address"] == "My Own Label"
    assert fake_geocoding_gateway.calls == []  # geocoder not consulted


async def test_create_polygon_not_geocoded(client, db_session, fake_geocoding_gateway):
    child, _, headers = await _setup(db_session)  # premium → polygon allowed
    polygon = {
        "name": "Yard", "zone_type": "other", "type": "polygon",
        "polygon_points": [
            {"lat": 18.50, "lng": 73.80},
            {"lat": 18.60, "lng": 73.80},
            {"lat": 18.60, "lng": 73.90},
        ],
    }
    resp = await _create(client, child.id, headers, polygon)
    assert resp.status_code == 201
    assert fake_geocoding_gateway.calls == []  # no single centre → skipped


async def test_create_null_geocode_leaves_address_unset(db_session, redis_client):
    # Service-level: a geocoder that finds nothing must not fail the create.
    child, parent, _ = await _setup(db_session)
    svc = GeofenceService(db_session, redis_client, FakeGeocodingGateway(address=None))
    geofence = await svc.create_geofence(
        parent, child.id,
        {"name": "Home", "zone_type": "home", "type": "circle",
         "center_lat": 18.52, "center_lng": 73.85, "radius_m": 200},
    )
    assert geofence.address is None


async def test_create_without_geocoder_unaffected(db_session, redis_client):
    # The default (no geocoder) path — existing geofence CRUD is unchanged.
    child, parent, _ = await _setup(db_session)
    svc = GeofenceService(db_session, redis_client)  # no geocoder
    geofence = await svc.create_geofence(
        parent, child.id,
        {"name": "Home", "zone_type": "home", "type": "circle",
         "center_lat": 18.52, "center_lng": 73.85, "radius_m": 200},
    )
    assert geofence.address is None
