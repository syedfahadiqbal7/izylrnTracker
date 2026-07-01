"""Tests for Razorpay integration (Sprint 6 Slice 2): checkout + HMAC webhook."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.alert import Alert
from app.models.user import Subscription, User
from app.services import payment_service, razorpay_gateway

CHECKOUT = "/api/v1/subscriptions/checkout"
WEBHOOK = "/api/v1/webhook/razorpay"
SECRET = "whsec_test_123"


async def _user(db, *, country="+91"):
    u = User(phone="+9198" + uuid.uuid4().hex[:8], country_code=country, subscription_tier="free")
    db.add(u)
    await db.flush()
    return u, {"Authorization": f"Bearer {create_access_token(str(u.id))}"}


@pytest.fixture
def razorpay_configured(monkeypatch):
    monkeypatch.setattr(payment_service.settings, "razorpay_plan_basic", "plan_basic_x")
    monkeypatch.setattr(payment_service.settings, "razorpay_plan_premium", "plan_premium_x")
    monkeypatch.setattr(payment_service.settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(razorpay_gateway.settings, "razorpay_webhook_secret", SECRET)


# --------------------------------------------------------------------------- #
# Checkout
# --------------------------------------------------------------------------- #
async def test_checkout_success(client, db_session, razorpay_configured, fake_razorpay_gateway):
    user, headers = await _user(db_session)
    resp = await client.post(CHECKOUT, headers=headers, json={"tier": "premium"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["gateway"] == "razorpay"
    assert data["subscription_id"] == "sub_TEST123"
    assert data["key_id"] == "rzp_test_key"
    # Gateway called with the right plan + our notes carrying the payer + tier.
    call = fake_razorpay_gateway.calls[0]
    assert call["plan_id"] == "plan_premium_x"
    assert call["notes"] == {"user_id": str(user.id), "tier": "premium"}


async def test_checkout_invalid_plan(client, db_session, razorpay_configured):
    _, headers = await _user(db_session)
    resp = await client.post(CHECKOUT, headers=headers, json={"tier": "free"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PLAN"


async def test_checkout_uae_routes_to_stripe_unavailable(client, db_session, razorpay_configured):
    _, headers = await _user(db_session, country="+971")
    resp = await client.post(CHECKOUT, headers=headers, json={"tier": "basic"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "GATEWAY_UNAVAILABLE"


async def test_checkout_plan_not_configured(client, db_session):
    _, headers = await _user(db_session)  # no razorpay_configured → plan ids empty
    resp = await client.post(CHECKOUT, headers=headers, json={"tier": "basic"})
    assert resp.status_code == 503
    assert resp.json()["code"] == "PLAN_NOT_CONFIGURED"


async def test_checkout_gateway_failure(
    client, db_session, razorpay_configured, fake_razorpay_gateway
):
    fake_razorpay_gateway.fail = True
    _, headers = await _user(db_session)
    resp = await client.post(CHECKOUT, headers=headers, json={"tier": "basic"})
    assert resp.status_code == 502
    assert resp.json()["code"] == "CHECKOUT_FAILED"


async def test_checkout_requires_auth(client):
    resp = await client.post(CHECKOUT, json={"tier": "basic"})
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Webhook
# --------------------------------------------------------------------------- #
def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _event(event, *, sub_id, user_id=None, tier="premium", current_end=None, notes=None):
    entity = {"id": sub_id, "status": "active"}
    if current_end is not None:
        entity["current_end"] = current_end
    entity["notes"] = notes if notes is not None else {"user_id": str(user_id), "tier": tier}
    return {"event": event, "payload": {"subscription": {"entity": entity}}}


async def _post(client, payload, *, event_id="evt_1", sign=True):
    body = json.dumps(payload).encode()
    sig = _sign(body) if sign else "deadbeef"
    return await client.post(
        WEBHOOK, content=body,
        headers={
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": event_id,
            "Content-Type": "application/json",
        },
    )


async def test_webhook_activation_grants_tier(client, db_session, razorpay_configured):
    user, _ = await _user(db_session)
    end = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    payload = _event("subscription.activated", sub_id="sub_A", user_id=user.id, current_end=end)
    resp = await _post(client, payload)
    assert resp.status_code == 200
    assert resp.json()["disposition"] == "activated"

    refreshed = await db_session.get(User, user.id)
    assert refreshed.subscription_tier == "premium"
    assert refreshed.subscription_expires_at is not None
    row = (await db_session.execute(
        select(Subscription).where(Subscription.gateway_sub_id == "sub_A")
    )).scalar_one()
    assert row.status == "active"
    assert row.tier == "premium"
    # Confirmation alert landed in the inbox.
    alerts = (await db_session.execute(
        select(Alert).where(Alert.user_id == user.id, Alert.type == "system")
    )).scalars().all()
    assert len(alerts) == 1


async def test_webhook_invalid_signature_401(client, db_session, razorpay_configured):
    user, _ = await _user(db_session)
    payload = _event("subscription.activated", sub_id="sub_B", user_id=user.id)
    resp = await _post(client, payload, sign=False)
    assert resp.status_code == 401
    assert resp.json()["code"] == "WEBHOOK_UNAUTHORIZED"
    refreshed = await db_session.get(User, user.id)
    assert refreshed.subscription_tier == "free"  # untouched


async def test_webhook_idempotent_same_event_id(client, db_session, razorpay_configured):
    user, _ = await _user(db_session)
    end = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    payload = _event("subscription.charged", sub_id="sub_C", user_id=user.id, current_end=end)
    first = await _post(client, payload, event_id="evt_dup")
    second = await _post(client, payload, event_id="evt_dup")
    assert first.json()["disposition"] == "activated"
    assert second.json()["disposition"] == "duplicate"
    # Only one confirmation alert despite the retry.
    count = (await db_session.execute(
        select(func.count()).select_from(Alert).where(Alert.user_id == user.id)
    )).scalar_one()
    assert count == 1


async def test_webhook_renewal_extends_period(client, db_session, razorpay_configured):
    user, _ = await _user(db_session)
    end1 = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    await _post(client, _event("subscription.activated", sub_id="sub_D", user_id=user.id,
                               current_end=end1), event_id="evt_a")
    end2 = int((datetime.now(UTC) + timedelta(days=60)).timestamp())
    await _post(client, _event("subscription.charged", sub_id="sub_D", user_id=user.id,
                               current_end=end2), event_id="evt_b")
    rows = (await db_session.execute(
        select(Subscription).where(Subscription.gateway_sub_id == "sub_D")
    )).scalars().all()
    assert len(rows) == 1  # upsert, not a second row
    assert int(rows[0].expires_at.timestamp()) == end2


async def test_webhook_cancel_keeps_tier_until_expiry(client, db_session, razorpay_configured):
    user, _ = await _user(db_session)
    end = int((datetime.now(UTC) + timedelta(days=15)).timestamp())
    await _post(client, _event("subscription.activated", sub_id="sub_E", user_id=user.id,
                               current_end=end), event_id="evt_act")
    resp = await _post(client, _event("subscription.cancelled", sub_id="sub_E", user_id=user.id),
                       event_id="evt_cancel")
    assert resp.json()["disposition"] == "cancelled"
    row = (await db_session.execute(
        select(Subscription).where(Subscription.gateway_sub_id == "sub_E")
    )).scalar_one()
    assert row.status == "cancelled"
    refreshed = await db_session.get(User, user.id)
    assert refreshed.subscription_tier == "premium"  # non-destructive — kept until expiry sweep


async def test_webhook_unresolvable_notes_ignored(client, db_session, razorpay_configured):
    resp = await _post(client, _event("subscription.activated", sub_id="sub_F", notes={}),
                       event_id="evt_x")
    assert resp.status_code == 200
    assert resp.json()["disposition"] == "unresolved"
