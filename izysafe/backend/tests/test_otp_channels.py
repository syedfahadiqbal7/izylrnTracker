"""Tests for the configurable OTP delivery channel (migration 0026).

An admin-managed, app-wide ordered fallback list (WhatsApp/SMS/Email), mirroring
the i18n/menu admin config. Covers the admin GET/PUT endpoints (role gate +
validation) and that send-otp honours the configured order — including Email,
which is skipped when the user has no email on file (parents authenticate by
phone; email is optional). The `otp_channels` row is seeded by migration 0026, so
the default GET reflects that committed seed; PUT upserts within the per-test
savepoint and is rolled back afterwards.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_secret
from app.models.integration import AppConfig
from app.models.school import School, SchoolAdmin
from app.models.user import OtpSession, User
from app.services.app_config_service import AppConfigService

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


# --------------------------------------------------------------- admin endpoint
async def test_get_defaults_to_whatsapp_then_sms(client, db_session):
    _, hdr = await _admin(db_session)
    resp = await client.get(OTP_CHANNELS, headers=hdr)
    assert resp.status_code == 200
    assert resp.json()["data"]["channels"] == ["whatsapp", "sms"]


async def test_put_updates_and_roundtrips(client, db_session):
    _, hdr = await _admin(db_session)
    resp = await client.put(
        OTP_CHANNELS, headers=hdr, json={"channels": ["email", "sms", "whatsapp"]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["channels"] == ["email", "sms", "whatsapp"]
    # persisted — a later GET reflects the edit
    got = await client.get(OTP_CHANNELS, headers=hdr)
    assert got.json()["data"]["channels"] == ["email", "sms", "whatsapp"]


@pytest.mark.parametrize(
    "bad",
    [[], ["carrier-pigeon"], ["sms", "sms"], ["whatsapp", "sms", "email", "sms"]],
)
async def test_put_rejects_invalid(client, db_session, bad):
    _, hdr = await _admin(db_session)
    resp = await client.put(OTP_CHANNELS, headers=hdr, json={"channels": bad})
    assert resp.status_code == 422


async def test_requires_admin(client, db_session):
    _, staff = await _admin(db_session, role="staff")
    assert (await client.get(OTP_CHANNELS, headers=staff)).status_code == 403
    assert (
        await client.put(OTP_CHANNELS, headers=staff, json={"channels": ["sms"]})
    ).status_code == 403


async def test_requires_auth(client):
    assert (await client.get(OTP_CHANNELS)).status_code == 401


# ------------------------------------------------------- delivery honours config
async def test_send_otp_honours_single_channel(client, db_session, fake_gateway):
    _, hdr = await _admin(db_session)
    await client.put(OTP_CHANNELS, headers=hdr, json={"channels": ["sms"]})
    resp = await client.post(SEND_OTP, json={"phone": PHONE_IN})
    assert resp.status_code == 200
    assert resp.json()["data"]["channel"] == "sms"
    assert fake_gateway.whatsapp_calls == []  # whatsapp not in the configured list
    assert len(fake_gateway.sms_calls) == 1


async def test_send_otp_email_channel(client, db_session, fake_gateway):
    _, hdr = await _admin(db_session)
    db_session.add(
        User(phone=PHONE_IN, country_code="+91", name="P", email="p@example.com")
    )
    await db_session.flush()
    await client.put(OTP_CHANNELS, headers=hdr, json={"channels": ["email", "sms"]})
    resp = await client.post(SEND_OTP, json={"phone": PHONE_IN})
    assert resp.status_code == 200
    assert resp.json()["data"]["channel"] == "email"
    assert fake_gateway.email_calls == [("p@example.com", fake_gateway.last_otp)]
    assert fake_gateway.sms_calls == []
    row = (
        await db_session.execute(select(OtpSession).where(OtpSession.phone == PHONE_IN))
    ).scalar_one()
    assert row.channel == "email"  # CHECK now allows 'email'


async def test_send_otp_email_skips_when_no_email(client, db_session, fake_gateway):
    _, hdr = await _admin(db_session)
    db_session.add(User(phone=PHONE_IN, country_code="+91", name="P", email=None))
    await db_session.flush()
    await client.put(OTP_CHANNELS, headers=hdr, json={"channels": ["email", "sms"]})
    resp = await client.post(SEND_OTP, json={"phone": PHONE_IN})
    assert resp.status_code == 200
    assert resp.json()["data"]["channel"] == "sms"  # email skipped, fell through
    assert fake_gateway.email_calls == []
    assert len(fake_gateway.sms_calls) == 1


async def test_send_otp_email_skips_when_no_account(client, db_session, fake_gateway):
    _, hdr = await _admin(db_session)
    # no user row for this phone → no email on file → skip to the next channel
    await client.put(OTP_CHANNELS, headers=hdr, json={"channels": ["email", "sms"]})
    resp = await client.post(SEND_OTP, json={"phone": PHONE_IN})
    assert resp.status_code == 200
    assert resp.json()["data"]["channel"] == "sms"
    assert fake_gateway.email_calls == []


# ------------------------------------------------------------------- service unit
async def test_service_defaults_when_row_missing(db_session):
    """get_otp_channels falls back to the default if the config row is absent."""
    row = await db_session.get(AppConfig, "otp_channels")
    if row is not None:
        await db_session.delete(row)
        await db_session.flush()
    assert await AppConfigService(db_session).get_otp_channels() == ["whatsapp", "sms"]


async def test_service_drops_unknown_channels(db_session):
    """A stale config listing a removed channel is sanitised on read."""
    await AppConfigService(db_session).set_otp_channels(["sms"])
    row = await db_session.get(AppConfig, "otp_channels")
    row.value = {"channels": ["sms", "pager"]}  # simulate a drifted value
    await db_session.flush()
    assert await AppConfigService(db_session).get_otp_channels() == ["sms"]
