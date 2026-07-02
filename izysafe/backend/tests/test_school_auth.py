"""Tests for School-admin auth + school profile (Sprint 8 Slice 1).

Covers env-gated seed, email+password login (+ brute-force guard), refresh rotation,
logout revocation, the `school_admin`-scoped auth dependency (rejects parent tokens),
staff invite (admin-only), admin listing, school config CRUD (admin-only), and
multi-tenant isolation.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_secret,
)
from app.models.school import School, SchoolAdmin
from app.models.user import User

SEED = "/api/v1/schools/seed"
LOGIN = "/api/v1/schools/auth/login"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _school(db, name="Green Valley School"):
    s = School(name=name, timezone="Asia/Kolkata")
    db.add(s)
    await db.flush()
    return s


async def _admin(db, school, *, email=None, role="admin", active=True, password="password123"):
    email = email or f"a-{uuid.uuid4().hex[:8]}@school.test"
    a = SchoolAdmin(
        school_id=school.id, email=email, password_hash=hash_secret(password),
        name="Admin", role=role, active=active,
    )
    db.add(a)
    await db.flush()
    return a


def _headers(admin):
    tok = create_access_token(str(admin.id), extra={"scope": "school_admin"})
    return {"Authorization": f"Bearer {tok}"}


def _seed_body(**over):
    body = {
        "secret": "test-seed", "school_name": "Green Valley",
        "admin_email": f"head-{uuid.uuid4().hex[:8]}@gv.test",
        "admin_password": "password123", "admin_name": "Head",
    }
    body.update(over)
    return body


# --------------------------------------------------------------------------- #
# Seed (env-gated bootstrap)
# --------------------------------------------------------------------------- #
async def test_seed_creates_school_and_admin(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "school_seed_secret", "test-seed")
    resp = await client.post(SEED, json=_seed_body())
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["admin"]["role"] == "admin"
    assert data["admin"]["school_id"] == data["school"]["id"]

    admin = (
        await db_session.execute(
            select(SchoolAdmin).where(SchoolAdmin.id == uuid.UUID(data["admin"]["id"]))
        )
    ).scalar_one()
    assert admin.password_hash != "password123"  # bcrypt-hashed, never plaintext


async def test_seed_disabled_when_secret_unset(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "school_seed_secret", "")
    resp = await client.post(SEED, json=_seed_body())
    assert resp.status_code == 403
    assert resp.json()["code"] == "SEED_DISABLED"


async def test_seed_wrong_secret(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "school_seed_secret", "test-seed")
    resp = await client.post(SEED, json=_seed_body(secret="nope"))
    assert resp.status_code == 403
    assert resp.json()["code"] == "SEED_FORBIDDEN"


async def test_seed_duplicate_email(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "school_seed_secret", "test-seed")
    body = _seed_body(admin_email="dup@gv.test")
    assert (await client.post(SEED, json=body)).status_code == 201
    resp = await client.post(SEED, json=body)
    assert resp.status_code == 409
    assert resp.json()["code"] == "EMAIL_TAKEN"


async def test_seed_short_password_rejected(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "school_seed_secret", "test-seed")
    resp = await client.post(SEED, json=_seed_body(admin_password="short"))
    assert resp.status_code == 422


async def test_seed_bad_email_rejected(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "school_seed_secret", "test-seed")
    resp = await client.post(SEED, json=_seed_body(admin_email="notanemail"))
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
async def test_login_success(client, db_session):
    school = await _school(db_session)
    admin = await _admin(db_session, school, email="me@gv.test", password="password123")
    resp = await client.post(LOGIN, json={"email": "me@gv.test", "password": "password123"})
    assert resp.status_code == 200, resp.text
    tokens = resp.json()["data"]
    claims = decode_token(tokens["access_token"], expected_type="access")
    assert claims["scope"] == "school_admin"
    assert claims["sub"] == str(admin.id)


async def test_login_email_case_insensitive(client, db_session):
    school = await _school(db_session)
    await _admin(db_session, school, email="case@gv.test", password="password123")
    resp = await client.post(LOGIN, json={"email": "CASE@GV.test", "password": "password123"})
    assert resp.status_code == 200


async def test_login_wrong_password(client, db_session):
    school = await _school(db_session)
    await _admin(db_session, school, email="wp@gv.test", password="password123")
    resp = await client.post(LOGIN, json={"email": "wp@gv.test", "password": "wrongpass1"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


async def test_login_unknown_email(client, db_session):
    resp = await client.post(LOGIN, json={"email": "ghost@gv.test", "password": "password123"})
    assert resp.status_code == 401


async def test_login_inactive_admin(client, db_session):
    school = await _school(db_session)
    await _admin(db_session, school, email="off@gv.test", password="password123", active=False)
    resp = await client.post(LOGIN, json={"email": "off@gv.test", "password": "password123"})
    assert resp.status_code == 401


async def test_login_rate_limited(client, db_session, redis_client):
    school = await _school(db_session)
    await _admin(db_session, school, email="rl@gv.test", password="password123")
    await redis_client.set(rk.school_login_rate("rl@gv.test"), settings.school_login_max_attempts)
    # Even a correct password is refused once the window is exhausted.
    resp = await client.post(LOGIN, json={"email": "rl@gv.test", "password": "password123"})
    assert resp.status_code == 429
    assert resp.json()["code"] == "TOO_MANY_ATTEMPTS"


# --------------------------------------------------------------------------- #
# Auth dependency (scope enforcement)
# --------------------------------------------------------------------------- #
async def test_admin_endpoint_requires_token(client, db_session):
    resp = await client.get("/api/v1/schools/admins/me")
    assert resp.status_code == 401


async def test_admin_endpoint_rejects_parent_token(client, db_session, auth_headers):
    # `auth_headers` is a normal parent access token — no school_admin scope.
    resp = await client.get("/api/v1/schools/admins/me", headers=auth_headers)
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_INVALID"


async def test_current_admin_identity(client, db_session):
    school = await _school(db_session)
    admin = await _admin(db_session, school, role="staff")
    resp = await client.get("/api/v1/schools/admins/me", headers=_headers(admin))
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == str(admin.id)
    assert resp.json()["data"]["role"] == "staff"


# --------------------------------------------------------------------------- #
# Refresh + logout
# --------------------------------------------------------------------------- #
async def test_refresh_rotates_and_revokes_old(client, db_session):
    school = await _school(db_session)
    await _admin(db_session, school, email="rt@gv.test", password="password123")
    tokens = (await client.post(LOGIN, json={"email": "rt@gv.test", "password": "password123"})).json()["data"]

    r1 = await client.post("/api/v1/schools/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200
    # The old refresh token is now denylisted.
    r2 = await client.post("/api/v1/schools/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401
    assert r2.json()["code"] == "TOKEN_REVOKED"


async def test_refresh_rejects_parent_refresh_token(client, db_session, user):
    # A parent refresh token has no school_admin scope.
    parent_refresh = create_refresh_token(str(user.id))
    resp = await client.post("/api/v1/schools/auth/refresh", json={"refresh_token": parent_refresh})
    assert resp.status_code == 401


async def test_logout_revokes_access(client, db_session):
    school = await _school(db_session)
    await _admin(db_session, school, email="lo@gv.test", password="password123")
    tokens = (await client.post(LOGIN, json={"email": "lo@gv.test", "password": "password123"})).json()["data"]
    hdr = {"Authorization": f"Bearer {tokens['access_token']}"}

    out = await client.request("DELETE", "/api/v1/schools/auth/logout", headers=hdr,
                               json={"refresh_token": tokens["refresh_token"]})
    assert out.status_code == 200
    # The revoked access token no longer works.
    after = await client.get("/api/v1/schools/admins/me", headers=hdr)
    assert after.status_code == 401
    assert after.json()["code"] == "TOKEN_REVOKED"


# --------------------------------------------------------------------------- #
# Staff invite + listing
# --------------------------------------------------------------------------- #
async def test_invite_staff_by_admin(client, db_session):
    school = await _school(db_session)
    admin = await _admin(db_session, school, role="admin")
    resp = await client.post("/api/v1/schools/admins", headers=_headers(admin),
                             json={"email": "staff@gv.test", "password": "password123", "role": "staff"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["role"] == "staff"
    assert data["school_id"] == str(school.id)


async def test_invite_requires_admin_role(client, db_session):
    school = await _school(db_session)
    staff = await _admin(db_session, school, role="staff")
    resp = await client.post("/api/v1/schools/admins", headers=_headers(staff),
                             json={"email": "x@gv.test", "password": "password123"})
    assert resp.status_code == 403


async def test_invite_duplicate_email(client, db_session):
    school = await _school(db_session)
    admin = await _admin(db_session, school, email="boss@gv.test", role="admin")
    resp = await client.post("/api/v1/schools/admins", headers=_headers(admin),
                             json={"email": "boss@gv.test", "password": "password123"})
    assert resp.status_code == 409


async def test_list_admins(client, db_session):
    school = await _school(db_session)
    admin = await _admin(db_session, school, role="admin")
    await _admin(db_session, school, role="staff")
    resp = await client.get("/api/v1/schools/admins", headers=_headers(admin))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


# --------------------------------------------------------------------------- #
# School profile / config
# --------------------------------------------------------------------------- #
async def test_get_my_school(client, db_session):
    school = await _school(db_session)
    admin = await _admin(db_session, school)
    resp = await client.get("/api/v1/schools/me", headers=_headers(admin))
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Green Valley School"


async def test_update_school_config_by_admin(client, db_session):
    school = await _school(db_session)
    admin = await _admin(db_session, school, role="admin")
    resp = await client.put("/api/v1/schools/me", headers=_headers(admin),
                            json={"on_time_before": "08:30:00", "holidays": ["2026-08-15"]})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["on_time_before"] == "08:30:00"
    assert data["holidays"] == ["2026-08-15"]


async def test_update_school_requires_admin(client, db_session):
    school = await _school(db_session)
    staff = await _admin(db_session, school, role="staff")
    resp = await client.put("/api/v1/schools/me", headers=_headers(staff), json={"name": "Nope"})
    assert resp.status_code == 403


async def test_update_school_bad_holiday_rejected(client, db_session):
    school = await _school(db_session)
    admin = await _admin(db_session, school, role="admin")
    resp = await client.put("/api/v1/schools/me", headers=_headers(admin),
                            json={"holidays": ["not-a-date"]})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Multi-tenant isolation
# --------------------------------------------------------------------------- #
async def test_admin_scoped_to_own_school(client, db_session):
    school_a = await _school(db_session, name="School A")
    school_b = await _school(db_session, name="School B")
    admin_a = await _admin(db_session, school_a, role="admin")
    await _admin(db_session, school_b, role="admin")
    await _admin(db_session, school_b, role="staff")

    me = await client.get("/api/v1/schools/me", headers=_headers(admin_a))
    assert me.json()["data"]["name"] == "School A"
    admins = await client.get("/api/v1/schools/admins", headers=_headers(admin_a))
    assert len(admins.json()["data"]) == 1  # only School A's admin
