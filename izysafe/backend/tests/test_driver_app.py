"""Tests for the driver app backend (Sprint 10 Slice 1).

Covers admin-side driver creation with/without an access code + set-code + phone
uniqueness; driver login (success, wrong code, unknown phone, inactive, rate limit);
the `driver`-scoped auth guard; refresh rotation + logout; and the today's-routes view
(own active routes only, with ordered stops + roster).
"""
from __future__ import annotations

import uuid

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.security import create_access_token, decode_token, hash_secret
from app.models.child import Child, FamilyMember
from app.models.school import (
    BusAssignment, BusRoute, BusRouteStop, Driver, School, SchoolAdmin, StudentEnrollment,
)
from app.models.user import User

DRIVERS_ADMIN = "/api/v1/schools/drivers"
DRIVER = "/api/v1/drivers"
LOGIN = "/api/v1/drivers/auth/login"


async def _school_admin(db, name="Green Valley"):
    school = School(name=name, timezone="UTC")
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(school_id=school.id, email=f"a-{uuid.uuid4().hex[:8]}@s.test",
                        password_hash=hash_secret("password123"), role="admin", active=True)
    db.add(admin)
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(admin.id), extra={'scope': 'school_admin'})}"}
    return school, admin, hdr


async def _driver(db, school, *, phone="+919812345678", code="drivercode1", active=True, name="Ravi"):
    d = Driver(school_id=school.id, name=name, phone=phone,
               password_hash=hash_secret(code) if code else None, active=active)
    db.add(d)
    await db.flush()
    return d


def _dhdr(driver):
    return {"Authorization": f"Bearer {create_access_token(str(driver.id), extra={'scope': 'driver'})}"}


# --------------------------------------------------------------------------- #
# Admin: create + set-code + phone uniqueness
# --------------------------------------------------------------------------- #
async def test_create_driver_with_code_enables_login(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    resp = await client.post(DRIVERS_ADMIN, headers=hdr,
                             json={"name": "Ravi", "phone": "+919811111111", "access_code": "secret12"})
    assert resp.status_code == 201, resp.text
    login = await client.post(LOGIN, json={"phone": "+919811111111", "code": "secret12"})
    assert login.status_code == 200


async def test_create_driver_without_code_cannot_login(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    await client.post(DRIVERS_ADMIN, headers=hdr, json={"name": "Ravi", "phone": "+919822222222"})
    login = await client.post(LOGIN, json={"phone": "+919822222222", "code": "whatever1"})
    assert login.status_code == 401


async def test_create_driver_duplicate_phone(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    body = {"name": "Ravi", "phone": "+919833333333"}
    assert (await client.post(DRIVERS_ADMIN, headers=hdr, json=body)).status_code == 201
    resp = await client.post(DRIVERS_ADMIN, headers=hdr, json=body)
    assert resp.status_code == 409
    assert resp.json()["code"] == "DRIVER_PHONE_TAKEN"


async def test_set_code_enables_login(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    driver = await _driver(db_session, school, phone="+919844444444", code=None)  # no code yet
    assert (await client.post(LOGIN, json={"phone": "+919844444444", "code": "x"})).status_code == 401
    resp = await client.post(f"{DRIVERS_ADMIN}/{driver.id}/set-code", headers=hdr, json={"access_code": "newcode12"})
    assert resp.status_code == 200
    assert (await client.post(LOGIN, json={"phone": "+919844444444", "code": "newcode12"})).status_code == 200


async def test_set_code_other_school_404(client, db_session):
    school_a, _, hdr_a = await _school_admin(db_session, "A")
    school_b, _, hdr_b = await _school_admin(db_session, "B")
    driver = await _driver(db_session, school_a, phone="+919855555555")
    resp = await client.post(f"{DRIVERS_ADMIN}/{driver.id}/set-code", headers=hdr_b, json={"access_code": "newcode12"})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Driver login
# --------------------------------------------------------------------------- #
async def test_login_success_scoped_token(client, db_session):
    school, _, _ = await _school_admin(db_session)
    driver = await _driver(db_session, school, phone="+919861111111", code="drivercode1")
    resp = await client.post(LOGIN, json={"phone": "+919861111111", "code": "drivercode1"})
    assert resp.status_code == 200
    claims = decode_token(resp.json()["data"]["access_token"], expected_type="access")
    assert claims["scope"] == "driver" and claims["sub"] == str(driver.id)


async def test_login_wrong_code(client, db_session):
    school, _, _ = await _school_admin(db_session)
    await _driver(db_session, school, phone="+919862222222", code="drivercode1")
    resp = await client.post(LOGIN, json={"phone": "+919862222222", "code": "wrongcode"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


async def test_login_unknown_phone(client, db_session):
    resp = await client.post(LOGIN, json={"phone": "+919800000000", "code": "drivercode1"})
    assert resp.status_code == 401


async def test_login_inactive_driver(client, db_session):
    school, _, _ = await _school_admin(db_session)
    await _driver(db_session, school, phone="+919863333333", code="drivercode1", active=False)
    resp = await client.post(LOGIN, json={"phone": "+919863333333", "code": "drivercode1"})
    assert resp.status_code == 401


async def test_login_rate_limited(client, db_session, redis_client):
    school, _, _ = await _school_admin(db_session)
    await _driver(db_session, school, phone="+919864444444", code="drivercode1")
    await redis_client.set(rk.driver_login_rate("+919864444444"), settings.driver_login_max_attempts)
    resp = await client.post(LOGIN, json={"phone": "+919864444444", "code": "drivercode1"})
    assert resp.status_code == 429


# --------------------------------------------------------------------------- #
# Auth guard + profile
# --------------------------------------------------------------------------- #
async def test_me_requires_token(client, db_session):
    assert (await client.get(f"{DRIVER}/me")).status_code == 401


async def test_me_rejects_admin_token(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    assert (await client.get(f"{DRIVER}/me", headers=admin_hdr)).status_code == 401


async def test_get_me(client, db_session):
    school, _, _ = await _school_admin(db_session)
    driver = await _driver(db_session, school, name="Ravi")
    resp = await client.get(f"{DRIVER}/me", headers=_dhdr(driver))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == str(driver.id) and data["name"] == "Ravi"
    assert data["school_id"] == str(school.id)


# --------------------------------------------------------------------------- #
# Refresh / logout
# --------------------------------------------------------------------------- #
async def test_refresh_rotates_and_revokes(client, db_session):
    school, _, _ = await _school_admin(db_session)
    await _driver(db_session, school, phone="+919871111111", code="drivercode1")
    tokens = (await client.post(LOGIN, json={"phone": "+919871111111", "code": "drivercode1"})).json()["data"]
    r1 = await client.post(f"{DRIVER}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200
    r2 = await client.post(f"{DRIVER}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401  # old refresh revoked


async def test_logout_revokes_access(client, db_session):
    school, _, _ = await _school_admin(db_session)
    await _driver(db_session, school, phone="+919872222222", code="drivercode1")
    tokens = (await client.post(LOGIN, json={"phone": "+919872222222", "code": "drivercode1"})).json()["data"]
    hdr = {"Authorization": f"Bearer {tokens['access_token']}"}
    out = await client.request("DELETE", f"{DRIVER}/auth/logout", headers=hdr,
                               json={"refresh_token": tokens["refresh_token"]})
    assert out.status_code == 200
    assert (await client.get(f"{DRIVER}/me", headers=hdr)).status_code == 401


# --------------------------------------------------------------------------- #
# Today's routes view
# --------------------------------------------------------------------------- #
async def test_my_routes_with_stops_and_roster(client, db_session):
    school, _, _ = await _school_admin(db_session)
    driver = await _driver(db_session, school)
    route = BusRoute(school_id=school.id, name="R1", driver_id=driver.id, active=True)
    db_session.add(route)
    await db_session.flush()
    db_session.add(BusRouteStop(route_id=route.id, name="B", lat=18.6, lng=73.9, seq=2))
    stop_a = BusRouteStop(route_id=route.id, name="A", lat=18.5, lng=73.8, seq=1)
    db_session.add(stop_a)
    # an enrolled + assigned child
    parent = User(phone="+9198" + f"{uuid.uuid4().int % 10**8:08d}", country_code="+91")
    db_session.add(parent)
    await db_session.flush()
    child = Child(name="Aryan")
    db_session.add(child)
    await db_session.flush()
    db_session.add(FamilyMember(child_id=child.id, user_id=parent.id, role="parent",
                                is_primary=True, can_view=True, can_call=True, can_manage=True))
    db_session.add(StudentEnrollment(school_id=school.id, child_id=child.id, parent_opt_in=True, bus_opt_in=True))
    db_session.add(BusAssignment(route_id=route.id, child_id=child.id, stop_id=stop_a.id))
    await db_session.flush()

    resp = await client.get(f"{DRIVER}/me/routes", headers=_dhdr(driver))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    r = data[0]
    assert r["name"] == "R1"
    assert [s["seq"] for s in r["stops"]] == [1, 2]  # ordered
    assert len(r["roster"]) == 1
    assert r["roster"][0]["child_name"] == "Aryan"


async def test_my_routes_only_own_and_active(client, db_session):
    school, _, _ = await _school_admin(db_session)
    driver = await _driver(db_session, school, phone="+919881111111")
    other = await _driver(db_session, school, phone="+919882222222", name="Other")
    db_session.add(BusRoute(school_id=school.id, name="Mine-active", driver_id=driver.id, active=True))
    db_session.add(BusRoute(school_id=school.id, name="Mine-inactive", driver_id=driver.id, active=False))
    db_session.add(BusRoute(school_id=school.id, name="Others", driver_id=other.id, active=True))
    await db_session.flush()

    data = (await client.get(f"{DRIVER}/me/routes", headers=_dhdr(driver))).json()["data"]
    assert [r["name"] for r in data] == ["Mine-active"]
