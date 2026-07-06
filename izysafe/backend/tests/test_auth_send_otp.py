"""Tests for POST /auth/send-otp (Feature 7, send slice).

Covers: WhatsApp happy path, SMS fallback, total send failure, phone-format
validation (IN/UAE + rejection), OTP persistence (hashed, not plaintext),
and rate limiting (per-phone via endpoint, per-IP via service)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import APIException
from app.core.security import verify_secret
from app.models.user import OtpSession
from app.services.otp_service import OtpService
from tests.fakes import FakeGateway

PHONE_IN = "+919876543210"
PHONE_AE = "+971501234567"


# --------------------------------------------------------------------------- #
# Endpoint tests
# --------------------------------------------------------------------------- #
async def test_send_otp_whatsapp_success(client, fake_gateway, db_session):
    resp = await client.post("/api/v1/auth/send-otp", json={"phone": PHONE_IN})
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body == {"success": True, "expires_in": 600, "channel": "whatsapp"}
    # delivered via WhatsApp only (no SMS fallback)
    assert len(fake_gateway.whatsapp_calls) == 1
    assert fake_gateway.sms_calls == []

    # an OTP session row exists, stored as a bcrypt hash (never plaintext)
    row = (await db_session.execute(select(OtpSession).where(OtpSession.phone == PHONE_IN))).scalar_one()
    assert row.channel == "whatsapp"
    assert row.otp_hash.startswith("$2b$")
    assert row.otp_hash != fake_gateway.last_otp
    assert verify_secret(fake_gateway.last_otp, row.otp_hash) is True


async def test_send_otp_sms_fallback(client, fake_gateway, db_session):
    fake_gateway.whatsapp_ok = False  # force fallback
    resp = await client.post("/api/v1/auth/send-otp", json={"phone": PHONE_IN})
    assert resp.status_code == 200
    assert resp.json()["data"]["channel"] == "sms"
    assert len(fake_gateway.whatsapp_calls) == 1
    assert len(fake_gateway.sms_calls) == 1

    row = (await db_session.execute(select(OtpSession).where(OtpSession.phone == PHONE_IN))).scalar_one()
    assert row.channel == "sms"


async def test_send_otp_dev_fallback(client, fake_gateway, db_session):
    # No provider configured (dev): the flow still succeeds so local dev/testing
    # can complete. The OTP is logged (channel="dev") and persisted.
    fake_gateway.whatsapp_ok = False
    fake_gateway.sms_ok = False
    resp = await client.post("/api/v1/auth/send-otp", json={"phone": PHONE_IN})
    assert resp.status_code == 200
    assert resp.json()["data"]["channel"] == "dev"
    row = (await db_session.execute(select(OtpSession).where(OtpSession.phone == PHONE_IN))).scalar_one()
    assert verify_secret(fake_gateway.last_otp, row.otp_hash) is True


async def test_send_otp_all_channels_fail_in_production(client, fake_gateway, db_session, monkeypatch):
    # In production there is NO dev fallback — a total delivery failure is a 502.
    from app.core.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    fake_gateway.whatsapp_ok = False
    fake_gateway.sms_ok = False
    resp = await client.post("/api/v1/auth/send-otp", json={"phone": PHONE_IN})
    assert resp.status_code == 502
    assert resp.json()["code"] == "OTP_SEND_FAILED"
    rows = (await db_session.execute(select(OtpSession).where(OtpSession.phone == PHONE_IN))).scalars().all()
    assert rows == []


async def test_send_otp_uae_phone_ok(client):
    resp = await client.post("/api/v1/auth/send-otp", json={"phone": PHONE_AE})
    assert resp.status_code == 200
    assert resp.json()["data"]["channel"] == "whatsapp"


@pytest.mark.parametrize("bad_phone", ["+91123", "+12025550100", "9876543210", "+971123", ""])
async def test_send_otp_invalid_phone(client, bad_phone):
    resp = await client.post("/api/v1/auth/send-otp", json={"phone": bad_phone})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] is True
    assert body["code"] == "INVALID_PHONE"


async def test_send_otp_phone_rate_limit(client):
    # limit is 5 per phone per window; the 6th must be rejected
    for _ in range(5):
        ok = await client.post("/api/v1/auth/send-otp", json={"phone": PHONE_IN})
        assert ok.status_code == 200
    blocked = await client.post("/api/v1/auth/send-otp", json={"phone": PHONE_IN})
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMIT_PHONE"


# --------------------------------------------------------------------------- #
# Service-level test: per-IP rate limit (20/window)
# --------------------------------------------------------------------------- #
async def test_send_otp_ip_rate_limit(db_session, redis_client):
    service = OtpService(db_session, redis_client, FakeGateway())
    ip = "203.0.113.7"
    # 20 distinct phones from the same IP succeed; the 21st trips the IP limit
    for i in range(20):
        await service.send_otp(f"+9198765{i:05d}", ip)
    with pytest.raises(APIException) as exc:
        await service.send_otp("+919999999999", ip)
    assert exc.value.code == "RATE_LIMIT_IP"
    assert exc.value.status_code == 429
