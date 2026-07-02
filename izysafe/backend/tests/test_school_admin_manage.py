"""Tests for school-admin management (Sprint 9 Slice 3).

Covers admin-only role/name updates, deactivate/reactivate, delete, and the guards:
no self-deactivate/delete, keep at least one active admin (last-admin demote blocked),
staff can't manage, tenant isolation, and deactivation blocking login + existing tokens.
"""
from __future__ import annotations

import uuid

from app.core.security import create_access_token, hash_secret
from app.models.school import School, SchoolAdmin

ADMINS = "/api/v1/schools/admins"
LOGIN = "/api/v1/schools/auth/login"


async def _school(db, name="Green Valley"):
    s = School(name=name, timezone="UTC")
    db.add(s)
    await db.flush()
    return s


async def _admin(db, school, *, role="admin", active=True, name="Adm", email=None, password="password123"):
    email = (email or f"a-{uuid.uuid4().hex[:8]}@s.test").lower()
    a = SchoolAdmin(school_id=school.id, email=email, password_hash=hash_secret(password),
                    name=name, role=role, active=active)
    db.add(a)
    await db.flush()
    return a


def _hdr(a):
    return {"Authorization": f"Bearer {create_access_token(str(a.id), extra={'scope': 'school_admin'})}"}


# --------------------------------------------------------------------------- #
# Update role / name
# --------------------------------------------------------------------------- #
async def test_demote_other_admin(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    b = await _admin(db_session, school, role="admin", name="Bob")
    resp = await client.patch(f"{ADMINS}/{b.id}", headers=_hdr(a), json={"role": "staff", "name": "Bobby"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["role"] == "staff"
    assert resp.json()["data"]["name"] == "Bobby"


async def test_promote_staff_to_admin(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    s = await _admin(db_session, school, role="staff")
    resp = await client.patch(f"{ADMINS}/{s.id}", headers=_hdr(a), json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["data"]["role"] == "admin"


async def test_manage_requires_admin_role(client, db_session):
    school = await _school(db_session)
    staff = await _admin(db_session, school, role="staff")
    target = await _admin(db_session, school, role="admin")
    resp = await client.patch(f"{ADMINS}/{target.id}", headers=_hdr(staff), json={"name": "X"})
    assert resp.status_code == 403


async def test_manage_other_school_404(client, db_session):
    school_a = await _school(db_session, "A")
    school_b = await _school(db_session, "B")
    a = await _admin(db_session, school_a, role="admin")
    b = await _admin(db_session, school_b, role="admin")
    resp = await client.patch(f"{ADMINS}/{b.id}", headers=_hdr(a), json={"name": "X"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "ADMIN_NOT_FOUND"


async def test_demote_last_admin_forbidden(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")  # the only admin
    resp = await client.patch(f"{ADMINS}/{a.id}", headers=_hdr(a), json={"role": "staff"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "LAST_ADMIN"


# --------------------------------------------------------------------------- #
# Deactivate / reactivate
# --------------------------------------------------------------------------- #
async def test_deactivate_admin(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    b = await _admin(db_session, school, role="admin", email="b@s.test")
    resp = await client.post(f"{ADMINS}/{b.id}/deactivate", headers=_hdr(a))
    assert resp.status_code == 200
    assert resp.json()["data"]["active"] is False


async def test_deactivate_self_forbidden(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    await _admin(db_session, school, role="admin")  # a second admin so it's not a last-admin case
    resp = await client.post(f"{ADMINS}/{a.id}/deactivate", headers=_hdr(a))
    assert resp.status_code == 403
    assert resp.json()["code"] == "CANNOT_MODIFY_SELF"


async def test_deactivated_admin_login_blocked(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    b = await _admin(db_session, school, role="admin", email="blocked@s.test", password="password123")
    await client.post(f"{ADMINS}/{b.id}/deactivate", headers=_hdr(a))
    resp = await client.post(LOGIN, json={"email": "blocked@s.test", "password": "password123"})
    assert resp.status_code == 401


async def test_deactivated_admin_token_rejected(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    b = await _admin(db_session, school, role="admin")
    b_hdr = _hdr(b)  # a token minted while active
    await client.post(f"{ADMINS}/{b.id}/deactivate", headers=_hdr(a))
    # The still-"valid" token no longer resolves an active admin.
    assert (await client.get(f"{ADMINS}/me", headers=b_hdr)).status_code == 401


async def test_reactivate_restores_login(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    b = await _admin(db_session, school, role="admin", email="re@s.test", password="password123")
    await client.post(f"{ADMINS}/{b.id}/deactivate", headers=_hdr(a))
    resp = await client.post(f"{ADMINS}/{b.id}/reactivate", headers=_hdr(a))
    assert resp.status_code == 200 and resp.json()["data"]["active"] is True
    assert (await client.post(LOGIN, json={"email": "re@s.test", "password": "password123"})).status_code == 200


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #
async def test_delete_admin(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    b = await _admin(db_session, school, role="admin")
    assert (await client.delete(f"{ADMINS}/{b.id}", headers=_hdr(a))).status_code == 200
    assert len((await client.get(ADMINS, headers=_hdr(a))).json()["data"]) == 1


async def test_delete_self_forbidden(client, db_session):
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    await _admin(db_session, school, role="admin")
    resp = await client.delete(f"{ADMINS}/{a.id}", headers=_hdr(a))
    assert resp.status_code == 403
    assert resp.json()["code"] == "CANNOT_MODIFY_SELF"


async def test_delete_requires_admin_role(client, db_session):
    school = await _school(db_session)
    staff = await _admin(db_session, school, role="staff")
    target = await _admin(db_session, school, role="admin")
    assert (await client.delete(f"{ADMINS}/{target.id}", headers=_hdr(staff))).status_code == 403


async def test_deactivate_only_staff_ok(client, db_session):
    # Deactivating a staff member never trips the last-admin guard.
    school = await _school(db_session)
    a = await _admin(db_session, school, role="admin")
    s = await _admin(db_session, school, role="staff")
    resp = await client.post(f"{ADMINS}/{s.id}/deactivate", headers=_hdr(a))
    assert resp.status_code == 200 and resp.json()["data"]["active"] is False
