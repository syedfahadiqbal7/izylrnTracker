"""Tests for POST /auth/verify-otp (Feature 7, verify slice).

Covers: happy path (new + existing user), wrong-OTP attempt counter up to the
3-attempt limit, expired OTP, no pending session, format + phone validation,
single-use session, and JWT token shape."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import decode_token, hash_secret
from app.models.child import Child, FamilyMember
from app.models.school import School, StudentEnrollment
from app.models.user import OtpSession, User

PHONE_IN = "+919876543210"
PHONE_AE = "+971501234567"


def _wrong(otp: str) -> str:
    return "000000" if otp != "000000" else "111111"


async def _send_and_get_otp(client, fake_gateway, phone=PHONE_IN) -> str:
    resp = await client.post("/api/v1/auth/send-otp", json={"phone": phone})
    assert resp.status_code == 200
    return fake_gateway.last_otp


async def _provision_enrolled(db, phone: str) -> User:
    """Model 1: a school-provisioned parent with an active enrollment — can log in."""
    parent = User(
        phone=phone, country_code="+971" if phone.startswith("+971") else "+91"
    )
    db.add(parent)
    await db.flush()
    child = Child(name="Kid")
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    school = School(name="S", timezone="Asia/Dubai")
    db.add(school)
    await db.flush()
    db.add(StudentEnrollment(school_id=school.id, child_id=child.id))
    await db.flush()
    return parent


# --------------------------------------------------------------------------- #
# Happy paths (Model 1: must be a provisioned, enrolled account)
# --------------------------------------------------------------------------- #
async def test_verify_enrolled_user_success(client, fake_gateway, db_session):
    await _provision_enrolled(db_session, PHONE_IN)
    otp = await _send_and_get_otp(client, fake_gateway)
    resp = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": otp})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["is_new_user"] is False
    assert data["token_type"] == "bearer"

    access = decode_token(data["access_token"], expected_type="access")
    refresh = decode_token(data["refresh_token"], expected_type="refresh")
    assert access["sub"] == refresh["sub"]

    user = (await db_session.execute(select(User).where(User.phone == PHONE_IN))).scalar_one()
    assert str(user.id) == access["sub"]


async def test_verify_existing_user_returns_same_id(client, fake_gateway, db_session):
    parent = await _provision_enrolled(db_session, PHONE_AE)
    otp = await _send_and_get_otp(client, fake_gateway, PHONE_AE)
    resp = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_AE, "otp": otp})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_new_user"] is False
    assert decode_token(data["access_token"])["sub"] == str(parent.id)


# --------------------------------------------------------------------------- #
# Model 1 access gate
# --------------------------------------------------------------------------- #
async def test_verify_unknown_phone_rejected(client, fake_gateway, db_session):
    # No account for this phone → no self-registration in Model 1.
    otp = await _send_and_get_otp(client, fake_gateway)
    resp = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": otp})
    assert resp.status_code == 403
    assert resp.json()["code"] == "NO_ACCOUNT"


async def test_verify_account_without_enrollment_rejected(client, fake_gateway, db_session):
    # Account exists but has no active enrollment (transferred / graduated) → blocked.
    db_session.add(User(phone=PHONE_IN, country_code="+91"))
    await db_session.flush()
    otp = await _send_and_get_otp(client, fake_gateway)
    resp = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": otp})
    assert resp.status_code == 403
    assert resp.json()["code"] == "NO_ACTIVE_ENROLLMENT"


# --------------------------------------------------------------------------- #
# Attempt limiting
# --------------------------------------------------------------------------- #
async def test_verify_wrong_otp_then_max_attempts(client, fake_gateway):
    otp = await _send_and_get_otp(client, fake_gateway)
    bad = _wrong(otp)

    # attempts 1 and 2 → OTP_INVALID with decreasing remaining
    for expected_remaining in (2, 1):
        r = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": bad})
        assert r.status_code == 400
        assert r.json()["code"] == "OTP_INVALID"
        assert f"{expected_remaining} attempts remaining" in r.json()["message"]

    # 3rd wrong attempt → locked out
    r = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": bad})
    assert r.status_code == 429
    assert r.json()["code"] == "OTP_MAX_ATTEMPTS"

    # even the correct OTP is now rejected (session is spent)
    r = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": otp})
    assert r.status_code == 429
    assert r.json()["code"] == "OTP_MAX_ATTEMPTS"


# --------------------------------------------------------------------------- #
# Expiry / missing session
# --------------------------------------------------------------------------- #
async def test_verify_expired_otp(client, db_session):
    db_session.add(
        OtpSession(
            phone=PHONE_IN,
            otp_hash=hash_secret("123456"),
            channel="whatsapp",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    await db_session.flush()
    r = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": "123456"})
    assert r.status_code == 400
    assert r.json()["code"] == "OTP_EXPIRED"


async def test_verify_no_session(client):
    r = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": "123456"})
    assert r.status_code == 400
    assert r.json()["code"] == "OTP_EXPIRED"


async def test_verify_single_use(client, fake_gateway, db_session):
    await _provision_enrolled(db_session, PHONE_IN)
    otp = await _send_and_get_otp(client, fake_gateway)
    ok = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": otp})
    assert ok.status_code == 200
    # reusing the same (now verified) OTP fails — no active session remains
    again = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": otp})
    assert again.status_code == 400
    assert again.json()["code"] == "OTP_EXPIRED"


# --------------------------------------------------------------------------- #
# Format / phone validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_otp", ["123", "12345a", "1234567", ""])
async def test_verify_invalid_otp_format(client, bad_otp):
    r = await client.post("/api/v1/auth/verify-otp", json={"phone": PHONE_IN, "otp": bad_otp})
    assert r.status_code == 400
    assert r.json()["code"] == "OTP_INVALID_FORMAT"


async def test_verify_invalid_phone(client):
    r = await client.post("/api/v1/auth/verify-otp", json={"phone": "+91123", "otp": "123456"})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_PHONE"
