"""Tests for bus roster & routes (Sprint 8 Slice 4, F28).

Covers CRUD for drivers, routes (+ driver/device ref validation), ordered stops
(+ seq uniqueness), and assignments (opted-in enrollee only, stop-on-route, dedup),
plus school tenant isolation and admin-scope auth.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import create_access_token, hash_secret
from app.models.child import Child, FamilyMember
from app.models.device import Device
from app.models.school import BusRoute, Driver, School, SchoolAdmin, StudentEnrollment
from app.models.user import User

BASE = "/api/v1/schools"


async def _school_admin(db, *, name="Green Valley"):
    school = School(name=name, timezone="UTC")
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(
        school_id=school.id, email=f"a-{uuid.uuid4().hex[:8]}@s.test",
        password_hash=hash_secret("password123"), role="admin", active=True,
    )
    db.add(admin)
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(admin.id), extra={'scope': 'school_admin'})}"}
    return school, admin, hdr


async def _enrolled_child(db, school, *, opt_in=True, name="Aryan"):
    parent = User(phone="+9198" + f"{uuid.uuid4().int % 10**8:08d}", country_code="+91")
    db.add(parent)
    await db.flush()
    child = Child(name=name)
    db.add(child)
    await db.flush()
    db.add(FamilyMember(child_id=child.id, user_id=parent.id, role="parent",
                        is_primary=True, can_view=True, can_call=True, can_manage=True))
    enr = StudentEnrollment(school_id=school.id, child_id=child.id, parent_opt_in=opt_in)
    db.add(enr)
    await db.flush()
    return child, str(enr.id)


async def _bus_device(db, school):
    dev = Device(
        school_id=school.id, child_id=None, name="Bus 1", device_type="bus",
        imei=uuid.uuid4().hex[:15],
    )
    db.add(dev)
    await db.flush()
    return dev


# --------------------------------------------------------------------------- #
# Drivers
# --------------------------------------------------------------------------- #
async def test_driver_crud(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    created = await client.post(f"{BASE}/drivers", headers=hdr, json={"name": "Ravi", "phone": "+919812345678"})
    assert created.status_code == 201, created.text
    did = created.json()["data"]["id"]
    # New driver: no access code yet, never logged in.
    assert created.json()["data"]["has_access_code"] is False
    assert created.json()["data"]["last_login_at"] is None

    assert len((await client.get(f"{BASE}/drivers", headers=hdr)).json()["data"]) == 1
    upd = await client.put(f"{BASE}/drivers/{did}", headers=hdr, json={"verified": True, "active": False})
    assert upd.json()["data"]["verified"] is True and upd.json()["data"]["active"] is False
    assert (await client.delete(f"{BASE}/drivers/{did}", headers=hdr)).status_code == 200
    assert len((await client.get(f"{BASE}/drivers", headers=hdr)).json()["data"]) == 0


async def test_driver_set_code_flags_has_access_code(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    did = (await client.post(f"{BASE}/drivers", headers=hdr, json={"name": "Ravi"})).json()["data"]["id"]
    resp = await client.post(f"{BASE}/drivers/{did}/set-code", headers=hdr, json={"access_code": "bus123"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["has_access_code"] is True


async def test_driver_create_with_access_code(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    resp = await client.post(
        f"{BASE}/drivers", headers=hdr, json={"name": "Sita", "access_code": "route9"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["has_access_code"] is True


async def test_driver_requires_admin_auth(client, db_session, auth_headers):
    resp = await client.post(f"{BASE}/drivers", headers=auth_headers, json={"name": "X"})
    assert resp.status_code == 401  # parent token → no school_admin scope


async def test_driver_tenant_isolation(client, db_session):
    _, _, hdr_a = await _school_admin(db_session, name="A")
    _, _, hdr_b = await _school_admin(db_session, name="B")
    did = (await client.post(f"{BASE}/drivers", headers=hdr_a, json={"name": "Ravi"})).json()["data"]["id"]
    assert (await client.put(f"{BASE}/drivers/{did}", headers=hdr_b, json={"name": "Z"})).status_code == 404


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
async def test_route_create_minimal(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    resp = await client.post(f"{BASE}/routes", headers=hdr, json={"name": "Route 1"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["device_id"] is None


async def test_route_with_valid_driver(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    did = (await client.post(f"{BASE}/drivers", headers=hdr, json={"name": "Ravi"})).json()["data"]["id"]
    resp = await client.post(f"{BASE}/routes", headers=hdr, json={"name": "R", "driver_id": did})
    assert resp.status_code == 201
    assert resp.json()["data"]["driver_id"] == did


async def test_route_foreign_driver_rejected(client, db_session):
    _, _, hdr_a = await _school_admin(db_session, name="A")
    _, _, hdr_b = await _school_admin(db_session, name="B")
    did = (await client.post(f"{BASE}/drivers", headers=hdr_b, json={"name": "Ravi"})).json()["data"]["id"]
    resp = await client.post(f"{BASE}/routes", headers=hdr_a, json={"name": "R", "driver_id": did})
    assert resp.status_code == 404
    assert resp.json()["code"] == "DRIVER_NOT_FOUND"


async def test_route_non_bus_device_rejected(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    child, _ = await _enrolled_child(db_session, school)
    watch = Device(child_id=child.id, name="Watch", device_type="watch", imei=uuid.uuid4().hex[:15])
    db_session.add(watch)
    await db_session.flush()
    resp = await client.post(f"{BASE}/routes", headers=hdr, json={"name": "R", "device_id": str(watch.id)})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_BUS_DEVICE"


async def test_route_bus_device_accepted(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    bus = await _bus_device(db_session, school)
    resp = await client.post(f"{BASE}/routes", headers=hdr, json={"name": "R", "device_id": str(bus.id)})
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["device_id"] == str(bus.id)


async def test_route_delete_cascades(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    rid = (await client.post(f"{BASE}/routes", headers=hdr, json={"name": "R"})).json()["data"]["id"]
    await client.post(f"{BASE}/routes/{rid}/stops", headers=hdr,
                      json={"name": "Stop A", "lat": 18.5, "lng": 73.8, "seq": 1})
    assert (await client.delete(f"{BASE}/routes/{rid}", headers=hdr)).status_code == 200
    assert (await client.get(f"{BASE}/routes/{rid}", headers=hdr)).status_code == 404


async def test_route_get_foreign_404(client, db_session):
    _, _, hdr_a = await _school_admin(db_session, name="A")
    _, _, hdr_b = await _school_admin(db_session, name="B")
    rid = (await client.post(f"{BASE}/routes", headers=hdr_a, json={"name": "R"})).json()["data"]["id"]
    assert (await client.get(f"{BASE}/routes/{rid}", headers=hdr_b)).status_code == 404


# --------------------------------------------------------------------------- #
# Stops
# --------------------------------------------------------------------------- #
async def _route(client, hdr, name="R"):
    return (await client.post(f"{BASE}/routes", headers=hdr, json={"name": name})).json()["data"]["id"]


async def test_stops_crud_and_order(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    rid = await _route(client, hdr)
    await client.post(f"{BASE}/routes/{rid}/stops", headers=hdr, json={"name": "B", "lat": 18.6, "lng": 73.9, "seq": 2})
    await client.post(f"{BASE}/routes/{rid}/stops", headers=hdr, json={"name": "A", "lat": 18.5, "lng": 73.8, "seq": 1})
    stops = (await client.get(f"{BASE}/routes/{rid}/stops", headers=hdr)).json()["data"]
    assert [s["seq"] for s in stops] == [1, 2]  # ordered by seq
    assert stops[0]["name"] == "A"


async def test_stop_duplicate_seq_rejected(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    rid = await _route(client, hdr)
    await client.post(f"{BASE}/routes/{rid}/stops", headers=hdr, json={"name": "A", "lat": 18.5, "lng": 73.8, "seq": 1})
    resp = await client.post(f"{BASE}/routes/{rid}/stops", headers=hdr, json={"name": "B", "lat": 18.6, "lng": 73.9, "seq": 1})
    assert resp.status_code == 409
    assert resp.json()["code"] == "STOP_SEQ_TAKEN"


async def test_stop_update_delete(client, db_session):
    _, _, hdr = await _school_admin(db_session)
    rid = await _route(client, hdr)
    sid = (await client.post(f"{BASE}/routes/{rid}/stops", headers=hdr,
                             json={"name": "A", "lat": 18.5, "lng": 73.8, "seq": 1})).json()["data"]["id"]
    upd = await client.put(f"{BASE}/stops/{sid}", headers=hdr, json={"name": "A2"})
    assert upd.json()["data"]["name"] == "A2"
    assert (await client.delete(f"{BASE}/stops/{sid}", headers=hdr)).status_code == 200


async def test_stop_on_foreign_route_404(client, db_session):
    _, _, hdr_a = await _school_admin(db_session, name="A")
    _, _, hdr_b = await _school_admin(db_session, name="B")
    rid = await _route(client, hdr_a)
    resp = await client.post(f"{BASE}/routes/{rid}/stops", headers=hdr_b,
                             json={"name": "A", "lat": 18.5, "lng": 73.8, "seq": 1})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Assignments
# --------------------------------------------------------------------------- #
async def test_assign_opted_in_child(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    child, enr_id = await _enrolled_child(db_session, school, opt_in=True)
    rid = await _route(client, hdr)
    resp = await client.post(f"{BASE}/routes/{rid}/assignments", headers=hdr, json={"enrollment_id": enr_id})
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["child_name"] == "Aryan"


async def test_assign_not_opted_in_rejected(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    child, enr_id = await _enrolled_child(db_session, school, opt_in=False)
    rid = await _route(client, hdr)
    resp = await client.post(f"{BASE}/routes/{rid}/assignments", headers=hdr, json={"enrollment_id": enr_id})
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_ENROLLED"


async def test_assign_duplicate_rejected(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    child, enr_id = await _enrolled_child(db_session, school)
    rid = await _route(client, hdr)
    body = {"enrollment_id": enr_id}
    assert (await client.post(f"{BASE}/routes/{rid}/assignments", headers=hdr, json=body)).status_code == 201
    resp = await client.post(f"{BASE}/routes/{rid}/assignments", headers=hdr, json=body)
    assert resp.status_code == 409
    assert resp.json()["code"] == "ALREADY_ASSIGNED"


async def test_assign_stop_not_on_route_rejected(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    child, enr_id = await _enrolled_child(db_session, school)
    rid = await _route(client, hdr, name="R1")
    other_rid = await _route(client, hdr, name="R2")
    other_stop = (await client.post(f"{BASE}/routes/{other_rid}/stops", headers=hdr,
                                    json={"name": "X", "lat": 18.5, "lng": 73.8, "seq": 1})).json()["data"]["id"]
    resp = await client.post(f"{BASE}/routes/{rid}/assignments", headers=hdr,
                             json={"enrollment_id": enr_id, "stop_id": other_stop})
    assert resp.status_code == 400
    assert resp.json()["code"] == "STOP_NOT_ON_ROUTE"


async def test_assign_foreign_enrollment_404(client, db_session):
    school_a, _, hdr_a = await _school_admin(db_session, name="A")
    school_b, _, _ = await _school_admin(db_session, name="B")
    child, enr_b = await _enrolled_child(db_session, school_b)  # enrolled at B
    rid = await _route(client, hdr_a)
    resp = await client.post(f"{BASE}/routes/{rid}/assignments", headers=hdr_a, json={"enrollment_id": enr_b})
    assert resp.status_code == 404
    assert resp.json()["code"] == "ENROLLMENT_NOT_FOUND"


async def test_list_and_unassign(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    child, enr_id = await _enrolled_child(db_session, school)
    rid = await _route(client, hdr)
    aid = (await client.post(f"{BASE}/routes/{rid}/assignments", headers=hdr, json={"enrollment_id": enr_id})).json()["data"]["id"]
    assert len((await client.get(f"{BASE}/routes/{rid}/assignments", headers=hdr)).json()["data"]) == 1
    assert (await client.delete(f"{BASE}/assignments/{aid}", headers=hdr)).status_code == 200
    assert len((await client.get(f"{BASE}/routes/{rid}/assignments", headers=hdr)).json()["data"]) == 0
