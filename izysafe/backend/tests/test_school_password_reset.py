"""Tests for school-admin password reset (Sprint 9 Slice 1).

Covers forgot-password (email dispatch + token storage, anti-enumeration for
unknown/inactive, per-email + per-IP rate limits) and reset (success + login flip,
invalid/expired token, single-use, weak password), end-to-end via FakeEmailGateway.
"""
from __future__ import annotations

import re
import uuid

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.security import hash_secret
from app.models.school import School, SchoolAdmin

FORGOT = "/api/v1/schools/auth/forgot-password"
RESET = "/api/v1/schools/auth/reset-password"
LOGIN = "/api/v1/schools/auth/login"


async def _admin(db, *, email=None, password="oldpassword1", active=True, role="admin"):
    email = (email or f"a-{uuid.uuid4().hex[:8]}@s.test").lower()
    school = School(name="Green Valley", timezone="UTC")
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(
        school_id=school.id, email=email, password_hash=hash_secret(password),
        name="Head", role=role, active=active,
    )
    db.add(admin)
    await db.flush()
    return admin


def _token_from(fake_email) -> str:
    assert fake_email.calls, "no email was sent"
    link_text = fake_email.calls[-1]["text"]
    m = re.search(r"token=([A-Za-z0-9_\-]+)", link_text)
    assert m, f"no token in email: {link_text}"
    return m.group(1)


# --------------------------------------------------------------------------- #
# Forgot password
# --------------------------------------------------------------------------- #
async def test_forgot_sends_email_and_stores_token(client, db_session, redis_client, fake_email_gateway):
    admin = await _admin(db_session, email="me@s.test")
    resp = await client.post(FORGOT, json={"email": "me@s.test"})
    assert resp.status_code == 200
    assert len(fake_email_gateway.calls) == 1
    assert fake_email_gateway.calls[0]["to"] == "me@s.test"
    # a token hash is stored in Redis
    import hashlib
    token = _token_from(fake_email_gateway)
    key = rk.pwreset_token(hashlib.sha256(token.encode()).hexdigest())
    assert await redis_client.get(key) == str(admin.id)


async def test_forgot_email_case_insensitive(client, db_session, fake_email_gateway):
    await _admin(db_session, email="case@s.test")
    resp = await client.post(FORGOT, json={"email": "CASE@S.test"})
    assert resp.status_code == 200
    assert len(fake_email_gateway.calls) == 1


async def test_forgot_unknown_email_no_send(client, db_session, fake_email_gateway):
    resp = await client.post(FORGOT, json={"email": "ghost@s.test"})
    assert resp.status_code == 200  # identical response
    assert fake_email_gateway.calls == []  # but nothing sent (anti-enumeration)


async def test_forgot_inactive_admin_no_send(client, db_session, fake_email_gateway):
    await _admin(db_session, email="off@s.test", active=False)
    resp = await client.post(FORGOT, json={"email": "off@s.test"})
    assert resp.status_code == 200
    assert fake_email_gateway.calls == []


async def test_forgot_response_identical_known_vs_unknown(client, db_session, fake_email_gateway):
    await _admin(db_session, email="known@s.test")
    known = await client.post(FORGOT, json={"email": "known@s.test"})
    unknown = await client.post(FORGOT, json={"email": "nobody@s.test"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()  # no enumeration signal


async def test_forgot_rate_limited_by_email(client, db_session, redis_client, fake_email_gateway):
    await _admin(db_session, email="rl@s.test")
    await redis_client.set(rk.pwreset_rate_email("rl@s.test"), settings.pwreset_rate_per_email)
    resp = await client.post(FORGOT, json={"email": "rl@s.test"})
    assert resp.status_code == 429
    assert resp.json()["code"] == "TOO_MANY_REQUESTS"


async def test_forgot_rate_limited_by_ip(client, db_session, redis_client, fake_email_gateway):
    await _admin(db_session, email="ip@s.test")
    await redis_client.set(rk.pwreset_rate_ip("127.0.0.1"), settings.pwreset_rate_per_ip)
    resp = await client.post(FORGOT, json={"email": "ip@s.test"})
    assert resp.status_code == 429


# --------------------------------------------------------------------------- #
# Reset password
# --------------------------------------------------------------------------- #
async def test_reset_success_updates_login(client, db_session, fake_email_gateway):
    await _admin(db_session, email="reset@s.test", password="oldpassword1")
    await client.post(FORGOT, json={"email": "reset@s.test"})
    token = _token_from(fake_email_gateway)

    resp = await client.post(RESET, json={"token": token, "new_password": "brandnewpass2"})
    assert resp.status_code == 200, resp.text

    # New password logs in; old one no longer works.
    ok = await client.post(LOGIN, json={"email": "reset@s.test", "password": "brandnewpass2"})
    assert ok.status_code == 200
    old = await client.post(LOGIN, json={"email": "reset@s.test", "password": "oldpassword1"})
    assert old.status_code == 401


async def test_reset_invalid_token(client, db_session):
    resp = await client.post(RESET, json={"token": "not-a-real-token-xxxxx", "new_password": "brandnewpass2"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_RESET_TOKEN"


async def test_reset_expired_token(client, db_session, redis_client, fake_email_gateway):
    await _admin(db_session, email="exp@s.test")
    await client.post(FORGOT, json={"email": "exp@s.test"})
    token = _token_from(fake_email_gateway)
    # Simulate expiry by dropping the token key before redemption.
    import hashlib
    await redis_client.delete(rk.pwreset_token(hashlib.sha256(token.encode()).hexdigest()))
    resp = await client.post(RESET, json={"token": token, "new_password": "brandnewpass2"})
    assert resp.status_code == 400


async def test_reset_single_use(client, db_session, fake_email_gateway):
    await _admin(db_session, email="once@s.test")
    await client.post(FORGOT, json={"email": "once@s.test"})
    token = _token_from(fake_email_gateway)
    assert (await client.post(RESET, json={"token": token, "new_password": "brandnewpass2"})).status_code == 200
    # Second use of the same token is rejected.
    resp = await client.post(RESET, json={"token": token, "new_password": "anotherpass3"})
    assert resp.status_code == 400


async def test_reset_weak_password_rejected(client, db_session, fake_email_gateway):
    await _admin(db_session, email="weak@s.test")
    await client.post(FORGOT, json={"email": "weak@s.test"})
    token = _token_from(fake_email_gateway)
    resp = await client.post(RESET, json={"token": token, "new_password": "short"})
    assert resp.status_code == 422  # min_length=8


async def test_staff_role_can_reset(client, db_session, fake_email_gateway):
    # Reset applies to both admin + staff SchoolAdmins.
    await _admin(db_session, email="staff@s.test", role="staff", password="oldpassword1")
    await client.post(FORGOT, json={"email": "staff@s.test"})
    token = _token_from(fake_email_gateway)
    assert (await client.post(RESET, json={"token": token, "new_password": "brandnewpass2"})).status_code == 200
    ok = await client.post(LOGIN, json={"email": "staff@s.test", "password": "brandnewpass2"})
    assert ok.status_code == 200
