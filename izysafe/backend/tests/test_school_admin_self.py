"""Tests for logged-in school-admin self-service (Sprint 9 Slice 2).

Password change (current-password check, weak-password rule, rate limit, login flip,
auth scope) and profile read/patch (name update, sensitive fields untouched).
"""
from __future__ import annotations

import uuid

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.security import create_access_token, hash_secret
from app.models.school import School, SchoolAdmin

PW = "/api/v1/schools/admins/me/password"
ME = "/api/v1/schools/admins/me"
LOGIN = "/api/v1/schools/auth/login"


async def _admin(db, *, email=None, password="oldpassword1", role="admin", name="Head"):
    email = (email or f"a-{uuid.uuid4().hex[:8]}@s.test").lower()
    school = School(name="Green Valley", timezone="UTC")
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(
        school_id=school.id, email=email, password_hash=hash_secret(password),
        name=name, role=role, active=True,
    )
    db.add(admin)
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(admin.id), extra={'scope': 'school_admin'})}"}
    return admin, hdr


# --------------------------------------------------------------------------- #
# Password change
# --------------------------------------------------------------------------- #
async def test_change_password_success_updates_login(client, db_session):
    admin, hdr = await _admin(db_session, email="chg@s.test", password="oldpassword1")
    resp = await client.post(PW, headers=hdr, json={"current_password": "oldpassword1", "new_password": "brandnewpass2"})
    assert resp.status_code == 200, resp.text
    # New password logs in; old one no longer works.
    assert (await client.post(LOGIN, json={"email": "chg@s.test", "password": "brandnewpass2"})).status_code == 200
    assert (await client.post(LOGIN, json={"email": "chg@s.test", "password": "oldpassword1"})).status_code == 401


async def test_change_password_wrong_current(client, db_session):
    _, hdr = await _admin(db_session, password="oldpassword1")
    resp = await client.post(PW, headers=hdr, json={"current_password": "wrongpass9", "new_password": "brandnewpass2"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "CURRENT_PASSWORD_INCORRECT"


async def test_change_password_weak_new(client, db_session):
    _, hdr = await _admin(db_session, password="oldpassword1")
    resp = await client.post(PW, headers=hdr, json={"current_password": "oldpassword1", "new_password": "short"})
    assert resp.status_code == 422


async def test_change_password_requires_auth(client, db_session):
    assert (await client.post(PW, json={"current_password": "x", "new_password": "brandnewpass2"})).status_code == 401


async def test_change_password_rejects_parent_token(client, db_session, auth_headers):
    resp = await client.post(PW, headers=auth_headers, json={"current_password": "x", "new_password": "brandnewpass2"})
    assert resp.status_code == 401  # no school_admin scope


async def test_change_password_rate_limited(client, db_session, redis_client):
    admin, hdr = await _admin(db_session, password="oldpassword1")
    await redis_client.set(rk.pwchange_rate(admin.id), settings.pwchange_max_attempts)
    resp = await client.post(PW, headers=hdr, json={"current_password": "oldpassword1", "new_password": "brandnewpass2"})
    assert resp.status_code == 429
    assert resp.json()["code"] == "TOO_MANY_ATTEMPTS"


async def test_change_password_clears_rate_on_success(client, db_session, redis_client):
    admin, hdr = await _admin(db_session, password="oldpassword1")
    # A couple of failed attempts, then a success resets the counter.
    await client.post(PW, headers=hdr, json={"current_password": "nope", "new_password": "brandnewpass2"})
    ok = await client.post(PW, headers=hdr, json={"current_password": "oldpassword1", "new_password": "brandnewpass2"})
    assert ok.status_code == 200
    assert await redis_client.get(rk.pwchange_rate(admin.id)) is None


# --------------------------------------------------------------------------- #
# Profile read / patch
# --------------------------------------------------------------------------- #
async def test_get_me(client, db_session):
    admin, hdr = await _admin(db_session, email="me@s.test", name="Head", role="admin")
    resp = await client.get(ME, headers=hdr)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == str(admin.id)
    assert data["email"] == "me@s.test"
    assert data["name"] == "Head"
    assert data["role"] == "admin"
    assert data["school_id"] == str(admin.school_id)


async def test_patch_name(client, db_session):
    _, hdr = await _admin(db_session, name="Old Name")
    resp = await client.patch(ME, headers=hdr, json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "New Name"
    # persisted
    assert (await client.get(ME, headers=hdr)).json()["data"]["name"] == "New Name"


async def test_patch_ignores_sensitive_fields(client, db_session):
    admin, hdr = await _admin(db_session, role="admin", name="Head")
    # Extra/sensitive fields are ignored (schema only accepts `name`).
    resp = await client.patch(ME, headers=hdr, json={"name": "Renamed", "role": "staff", "email": "hijack@s.test"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Renamed"
    assert data["role"] == "admin"                 # unchanged
    assert data["email"] == admin.email            # unchanged


async def test_patch_requires_auth(client, db_session):
    assert (await client.patch(ME, json={"name": "X"})).status_code == 401
