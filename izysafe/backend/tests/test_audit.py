"""Tests for audit log + last-login (Sprint 10 Slice 2).

Verifies audit rows are written (in-transaction) for the curated actions, that
last_login_at is stamped, and the /schools/audit endpoint (role='admin', filters,
pagination, tenant-scoped) works.
"""
from __future__ import annotations

import uuid

from app.core.security import create_access_token, hash_secret
from app.models.child import Child, FamilyMember
from app.models.school import Driver, School, SchoolAdmin, StudentEnrollment
from app.models.user import User

AUDIT = "/api/v1/schools/audit"


async def _school_admin(db, *, name="Green Valley", role="admin", email=None, password="password123"):
    school = School(name=name, timezone="UTC")
    db.add(school)
    await db.flush()
    email = (email or f"a-{uuid.uuid4().hex[:8]}@s.test").lower()
    admin = SchoolAdmin(school_id=school.id, email=email, password_hash=hash_secret(password),
                        role=role, active=True)
    db.add(admin)
    await db.flush()
    return school, admin, email, password


def _hdr(a):
    return {"Authorization": f"Bearer {create_access_token(str(a.id), extra={'scope': 'school_admin'})}"}


async def _actions(client, hdr, **params):
    resp = await client.get(AUDIT, headers=hdr, params=params)
    assert resp.status_code == 200, resp.text
    return resp, [r["action"] for r in resp.json()["data"]]


# --------------------------------------------------------------------------- #
# Logins
# --------------------------------------------------------------------------- #
async def test_admin_login_audited_and_stamped(client, db_session):
    school, admin, email, pw = await _school_admin(db_session, email="me@s.test")
    assert (await client.post("/api/v1/schools/auth/login", json={"email": email, "password": pw})).status_code == 200
    _, actions = await _actions(client, _hdr(admin))
    assert "admin.login" in actions
    me = await client.get("/api/v1/schools/admins/me", headers=_hdr(admin))
    assert me.json()["data"]["last_login_at"] is not None


async def test_driver_login_audited_and_stamped(client, db_session):
    school, admin, _, _ = await _school_admin(db_session)
    driver = Driver(school_id=school.id, name="Ravi", phone="+919812345678",
                    password_hash=hash_secret("drivercode1"), active=True)
    db_session.add(driver)
    await db_session.flush()
    assert (await client.post("/api/v1/drivers/auth/login",
                              json={"phone": "+919812345678", "code": "drivercode1"})).status_code == 200
    _, actions = await _actions(client, _hdr(admin))
    assert "driver.login" in actions
    dhdr = {"Authorization": f"Bearer {create_access_token(str(driver.id), extra={'scope': 'driver'})}"}
    assert (await client.get("/api/v1/drivers/me", headers=dhdr)).json()["data"]["last_login_at"] is not None


# --------------------------------------------------------------------------- #
# Admin management + config
# --------------------------------------------------------------------------- #
async def test_admin_management_audited(client, db_session):
    school, admin, _, _ = await _school_admin(db_session)
    other = SchoolAdmin(school_id=school.id, email=f"o-{uuid.uuid4().hex[:6]}@s.test",
                        password_hash=hash_secret("password123"), role="admin", active=True)
    db_session.add(other)
    await db_session.flush()
    await client.post(f"/api/v1/schools/admins/{other.id}/deactivate", headers=_hdr(admin))
    resp, actions = await _actions(client, _hdr(admin), action="admin.deactivate")
    assert actions == ["admin.deactivate"]
    assert resp.json()["data"][0]["entity_id"] == str(other.id)


async def test_school_config_update_audited(client, db_session):
    school, admin, _, _ = await _school_admin(db_session)
    await client.put("/api/v1/schools/me", headers=_hdr(admin), json={"on_time_before": "08:30:00"})
    _, actions = await _actions(client, _hdr(admin))
    assert "school.config_update" in actions


# --------------------------------------------------------------------------- #
# Enrollment consent (parent actor, school-scoped)
# --------------------------------------------------------------------------- #
async def test_consent_opt_in_audited(client, db_session):
    school, admin, _, _ = await _school_admin(db_session)
    parent = User(phone="+919833333333", country_code="+91")
    db_session.add(parent)
    await db_session.flush()
    child = Child(name="Aryan")
    db_session.add(child)
    await db_session.flush()
    db_session.add(FamilyMember(child_id=child.id, user_id=parent.id, role="parent",
                                is_primary=True, can_view=True, can_call=True, can_manage=True))
    await db_session.flush()
    await client.post("/api/v1/schools/students", headers=_hdr(admin), json={"phone": "+919833333333"})
    p_hdr = {"Authorization": f"Bearer {create_access_token(str(parent.id))}"}
    eid = (await client.get("/api/v1/enrollments", headers=p_hdr)).json()["data"][0]["id"]
    await client.put(f"/api/v1/enrollments/{eid}", headers=p_hdr, json={"parent_opt_in": True})

    resp, actions = await _actions(client, _hdr(admin), action="enrollment.opt_in")
    assert actions == ["enrollment.opt_in"]
    assert resp.json()["data"][0]["actor_type"] == "parent"


# --------------------------------------------------------------------------- #
# Driver create + trip actions
# --------------------------------------------------------------------------- #
async def test_driver_and_trip_actions_audited(client, db_session):
    school, admin, _, _ = await _school_admin(db_session)
    # Create driver via API (driver.create) with a code.
    cr = await client.post("/api/v1/schools/drivers", headers=_hdr(admin),
                           json={"name": "Ravi", "phone": "+919844444444", "access_code": "drivercode1"})
    driver_id = cr.json()["data"]["id"]
    # Seed a route + start/end a trip via the driver.
    from app.models.school import BusRoute
    route = BusRoute(school_id=school.id, name="R1", driver_id=uuid.UUID(driver_id), active=True)
    db_session.add(route)
    await db_session.flush()
    dhdr = {"Authorization": f"Bearer {create_access_token(driver_id, extra={'scope': 'driver'})}"}
    await client.post("/api/v1/drivers/me/trip/start", headers=dhdr, json={"route_id": str(route.id)})
    await client.post("/api/v1/drivers/me/trip/end", headers=dhdr)

    _, actions = await _actions(client, _hdr(admin))
    assert {"driver.create", "driver.trip.start", "driver.trip.end"} <= set(actions)


# --------------------------------------------------------------------------- #
# Endpoint guards + scoping
# --------------------------------------------------------------------------- #
async def test_audit_requires_admin_role(client, db_session):
    school, _, _, _ = await _school_admin(db_session)
    staff = SchoolAdmin(school_id=school.id, email=f"s-{uuid.uuid4().hex[:6]}@s.test",
                        password_hash=hash_secret("password123"), role="staff", active=True)
    db_session.add(staff)
    await db_session.flush()
    assert (await client.get(AUDIT, headers=_hdr(staff))).status_code == 403


async def test_audit_tenant_scoped(client, db_session):
    school_a, admin_a, _, _ = await _school_admin(db_session, name="A")
    _, admin_b, _, _ = await _school_admin(db_session, name="B")
    await client.put("/api/v1/schools/me", headers=_hdr(admin_a), json={"on_time_before": "08:30:00"})
    # Admin B sees none of A's entries.
    assert (await client.get(AUDIT, headers=_hdr(admin_b))).json()["meta"]["total"] == 0


async def test_audit_pagination_and_filter(client, db_session):
    school, admin, _, _ = await _school_admin(db_session)
    for t in ("08:30:00", "08:31:00", "08:32:00"):
        await client.put("/api/v1/schools/me", headers=_hdr(admin), json={"on_time_before": t})
    resp, _ = await _actions(client, _hdr(admin), action="school.config_update", limit=2)
    assert resp.json()["meta"]["total"] == 3
    assert len(resp.json()["data"]) == 2  # page size
