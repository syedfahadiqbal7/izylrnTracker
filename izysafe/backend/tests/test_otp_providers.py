"""Tests for admin-managed OTP provider credentials (migration 0026, app_config).

Per-channel credentials (MSG91/Twilio/SMTP) are editable from the admin panel and
override the environment (panel wins, env is the fallback). Secrets are masked on
read and a blank secret on write keeps the stored value. Covers the masked GET, the
per-channel PUTs, precedence, delivery using the resolved creds, and the test-send.
"""
from __future__ import annotations

import uuid

from app.core.config import settings
from app.core.security import create_access_token, hash_secret
from app.models.school import School, SchoolAdmin
from app.services.app_config_service import AppConfigService

PROVIDERS = "/api/v1/schools/otp-providers"
OTP_CHANNELS = "/api/v1/schools/otp-channels"
SEND_OTP = "/api/v1/auth/send-otp"
PHONE_IN = "+919876543210"


async def _admin(db, *, role="admin"):
    school = School(name="Green Valley", timezone="UTC")
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(
        school_id=school.id, email=f"a-{uuid.uuid4().hex[:8]}@s.test",
        password_hash=hash_secret("password1"), name="Head", role=role, active=True,
    )
    db.add(admin)
    await db.flush()
    hdr = {
        "Authorization": f"Bearer "
        f"{create_access_token(str(admin.id), extra={'scope': 'school_admin'})}"
    }
    return admin, hdr


# ---------------------------------------------------------------- masked read
async def test_get_providers_masked_defaults(client, db_session):
    _, hdr = await _admin(db_session)
    data = (await client.get(PROVIDERS, headers=hdr)).json()["data"]
    # secrets never returned raw — only *_set flags
    assert data["whatsapp"]["auth_key_set"] is False
    assert "auth_key" not in data["whatsapp"]
    assert data["sms"]["auth_token_set"] is False
    assert "auth_token" not in data["sms"]
    assert data["email"]["password_set"] is False
    assert "password" not in data["email"]
    # non-secret env defaults surface
    assert data["email"]["port"] == settings.smtp_port
    assert data["email"]["use_tls"] is settings.smtp_use_tls


async def test_put_whatsapp_sets_and_masks(client, db_session):
    _, hdr = await _admin(db_session)
    resp = await client.put(
        f"{PROVIDERS}/whatsapp", headers=hdr,
        json={
            "auth_key": "msg91key",
            "template": "izysafe_otp",
            "integrated_number": "+971500000000",
        },
    )
    assert resp.status_code == 200, resp.text
    wa = resp.json()["data"]["whatsapp"]
    assert wa["auth_key_set"] is True
    assert wa["template"] == "izysafe_otp"
    assert wa["integrated_number"] == "+971500000000"
    assert "auth_key" not in wa


async def test_put_blank_secret_keeps_existing(client, db_session):
    _, hdr = await _admin(db_session)
    await client.put(f"{PROVIDERS}/sms", headers=hdr,
                     json={"account_sid": "AC1", "auth_token": "tok1", "from_number": "+111"})
    # update only a non-secret field; auth_token omitted → kept
    resp = await client.put(f"{PROVIDERS}/sms", headers=hdr, json={"from_number": "+222"})
    sms = resp.json()["data"]["sms"]
    assert sms["auth_token_set"] is True
    assert sms["from_number"] == "+222"
    assert sms["account_sid"] == "AC1"


async def test_requires_admin(client, db_session):
    _, staff = await _admin(db_session, role="staff")
    assert (await client.get(PROVIDERS, headers=staff)).status_code == 403
    assert (
        await client.put(f"{PROVIDERS}/sms", headers=staff, json={"from_number": "+1"})
    ).status_code == 403
    assert (
        await client.post(f"{PROVIDERS}/sms/test", headers=staff, json={"recipient": PHONE_IN})
    ).status_code == 403


# ------------------------------------------------------------ precedence (unit)
async def test_resolve_prefers_db_over_env(db_session, monkeypatch):
    monkeypatch.setattr(settings, "twilio_sid", "envsid")
    monkeypatch.setattr(settings, "twilio_token", "envtoken")
    svc = AppConfigService(db_session)
    await svc.set_otp_provider("sms", {"auth_token": "dbtoken"})
    resolved = (await svc.resolve_otp_providers())["sms"]
    assert resolved["auth_token"] == "dbtoken"       # DB wins
    assert resolved["account_sid"] == "envsid"        # env fills the gap


# --------------------------------------------------------- delivery uses creds
async def test_send_otp_passes_resolved_cfg(client, db_session, fake_gateway):
    _, hdr = await _admin(db_session)
    await client.put(f"{PROVIDERS}/sms", headers=hdr,
                     json={"account_sid": "AC9", "auth_token": "tok9", "from_number": "+99999"})
    await client.put(OTP_CHANNELS, headers=hdr, json={"channels": ["sms"]})
    resp = await client.post(SEND_OTP, json={"phone": PHONE_IN})
    assert resp.status_code == 200 and resp.json()["data"]["channel"] == "sms"
    sms_cfgs = [cfg for ch, cfg in fake_gateway.cfgs if ch == "sms"]
    assert sms_cfgs and sms_cfgs[-1]["from_number"] == "+99999"
    assert sms_cfgs[-1]["auth_token"] == "tok9"


# --------------------------------------------------------------- test-send
async def test_test_send_reports_provider_result(client, db_session, fake_gateway):
    _, hdr = await _admin(db_session)
    ok = await client.post(f"{PROVIDERS}/whatsapp/test", headers=hdr, json={"recipient": PHONE_IN})
    assert ok.status_code == 200 and ok.json()["data"]["sent"] is True
    assert fake_gateway.whatsapp_calls  # a real send attempt was made

    fake_gateway.sms_ok = False
    fail = await client.post(f"{PROVIDERS}/sms/test", headers=hdr, json={"recipient": PHONE_IN})
    assert fail.status_code == 200 and fail.json()["data"]["sent"] is False


async def test_test_send_email_channel(client, db_session, fake_gateway):
    _, hdr = await _admin(db_session)
    resp = await client.post(
        f"{PROVIDERS}/email/test", headers=hdr, json={"recipient": "admin@example.com"}
    )
    assert resp.status_code == 200 and resp.json()["data"]["sent"] is True
    assert fake_gateway.email_calls[-1][0] == "admin@example.com"


async def test_test_send_unknown_channel_404(client, db_session):
    _, hdr = await _admin(db_session)
    resp = await client.post(
        f"{PROVIDERS}/telegram/test", headers=hdr, json={"recipient": PHONE_IN}
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "UNKNOWN_CHANNEL"
