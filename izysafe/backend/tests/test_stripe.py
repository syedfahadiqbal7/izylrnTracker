"""Tests for Stripe integration (Sprint 6 Slice 3): checkout + HMAC webhook (UAE)."""
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
from app.services import payment_service, stripe_gateway

CHECKOUT = "/api/v1/subscriptions/checkout"
WEBHOOK = "/api/v1/webhook/stripe"
SECRET = "whsec_stripe_test"


async def _user(db, *, country="+971"):
    u = User(phone="+9715" + uuid.uuid4().hex[:7], country_code=country, subscription_tier="free")
    db.add(u)
    await db.flush()
    return u, {"Authorization": f"Bearer {create_access_token(str(u.id))}"}


@pytest.fixture
def stripe_configured(monkeypatch):
    monkeypatch.setattr(payment_service.settings, "stripe_price_basic", "price_basic_x")
    monkeypatch.setattr(payment_service.settings, "stripe_price_premium", "price_premium_x")
    monkeypatch.setattr(stripe_gateway.settings, "stripe_webhook_secret", SECRET)


# --------------------------------------------------------------------------- #
# Checkout
# --------------------------------------------------------------------------- #
async def test_checkout_success(client, db_session, stripe_configured, fake_stripe_gateway):
    user, headers = await _user(db_session)
    resp = await client.post(CHECKOUT, headers=headers, json={"tier": "premium"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["gateway"] == "stripe"
    assert data["reference_id"] == "cs_test_123"
    assert data["checkout_url"].startswith("https://checkout.stripe.com/")
    assert data["key_id"] is None
    call = fake_stripe_gateway.calls[0]
    assert call["price_id"] == "price_premium_x"
    assert call["metadata"] == {"user_id": str(user.id), "tier": "premium"}


async def test_checkout_india_routes_to_razorpay(client, db_session, stripe_configured):
    # India user → Razorpay branch; no razorpay plan configured → 503 (not Stripe).
    _, headers = await _user(db_session, country="+91")
    resp = await client.post(CHECKOUT, headers=headers, json={"tier": "basic"})
    assert resp.status_code == 503
    assert resp.json()["code"] == "PLAN_NOT_CONFIGURED"


async def test_checkout_plan_not_configured(client, db_session):
    _, headers = await _user(db_session)  # no stripe_configured → price ids empty
    resp = await client.post(CHECKOUT, headers=headers, json={"tier": "basic"})
    assert resp.status_code == 503
    assert resp.json()["code"] == "PLAN_NOT_CONFIGURED"


async def test_checkout_gateway_failure(
    client, db_session, stripe_configured, fake_stripe_gateway
):
    fake_stripe_gateway.fail = True
    _, headers = await _user(db_session)
    resp = await client.post(CHECKOUT, headers=headers, json={"tier": "basic"})
    assert resp.status_code == 502
    assert resp.json()["code"] == "CHECKOUT_FAILED"


# --------------------------------------------------------------------------- #
# Webhook
# --------------------------------------------------------------------------- #
def _sign(body: bytes, timestamp: str = "1700000000") -> str:
    sig = hmac.new(SECRET.encode(), (timestamp + ".").encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def _event(event_type, *, evt_id, sub_id, user_id=None, tier="premium",
           status="active", current_period_end=None, metadata=None):
    obj = {"id": sub_id, "status": status}
    if current_period_end is not None:
        obj["current_period_end"] = current_period_end
    obj["metadata"] = metadata if metadata is not None else {"user_id": str(user_id), "tier": tier}
    return {"id": evt_id, "type": event_type, "data": {"object": obj}}


async def _post(client, payload, *, sign=True):
    body = json.dumps(payload).encode()
    header = _sign(body) if sign else "t=1700000000,v1=deadbeef"
    return await client.post(
        WEBHOOK, content=body,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )


async def test_webhook_activation_grants_tier(client, db_session, stripe_configured):
    user, _ = await _user(db_session)
    end = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    payload = _event("customer.subscription.created", evt_id="evt_1", sub_id="sub_S1",
                     user_id=user.id, current_period_end=end)
    resp = await _post(client, payload)
    assert resp.status_code == 200
    assert resp.json()["disposition"] == "activated"

    refreshed = await db_session.get(User, user.id)
    assert refreshed.subscription_tier == "premium"
    row = (await db_session.execute(
        select(Subscription).where(Subscription.gateway_sub_id == "sub_S1")
    )).scalar_one()
    assert row.status == "active"
    assert row.gateway == "stripe"
    alerts = (await db_session.execute(
        select(func.count()).select_from(Alert).where(Alert.user_id == user.id)
    )).scalar_one()
    assert alerts == 1


async def test_webhook_invalid_signature_401(client, db_session, stripe_configured):
    user, _ = await _user(db_session)
    payload = _event("customer.subscription.created", evt_id="evt_2", sub_id="sub_S2",
                     user_id=user.id)
    resp = await _post(client, payload, sign=False)
    assert resp.status_code == 401
    assert resp.json()["code"] == "WEBHOOK_UNAUTHORIZED"
    refreshed = await db_session.get(User, user.id)
    assert refreshed.subscription_tier == "free"


async def test_webhook_idempotent(client, db_session, stripe_configured):
    user, _ = await _user(db_session)
    end = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    payload = _event("customer.subscription.updated", evt_id="evt_dup", sub_id="sub_S3",
                     user_id=user.id, current_period_end=end)
    first = await _post(client, payload)
    second = await _post(client, payload)
    assert first.json()["disposition"] == "activated"
    assert second.json()["disposition"] == "duplicate"
    count = (await db_session.execute(
        select(func.count()).select_from(Alert).where(Alert.user_id == user.id)
    )).scalar_one()
    assert count == 1


async def test_webhook_past_due_keeps_tier(client, db_session, stripe_configured):
    user, _ = await _user(db_session)
    end = int((datetime.now(UTC) + timedelta(days=15)).timestamp())
    await _post(client, _event("customer.subscription.created", evt_id="evt_a", sub_id="sub_S4",
                               user_id=user.id, current_period_end=end))
    resp = await _post(client, _event("customer.subscription.updated", evt_id="evt_b",
                                      sub_id="sub_S4", user_id=user.id, status="past_due"))
    assert resp.json()["disposition"] == "past_due"
    row = (await db_session.execute(
        select(Subscription).where(Subscription.gateway_sub_id == "sub_S4")
    )).scalar_one()
    assert row.status == "past_due"
    refreshed = await db_session.get(User, user.id)
    assert refreshed.subscription_tier == "premium"  # kept until expiry


async def test_webhook_deleted_cancels_keeps_tier(client, db_session, stripe_configured):
    user, _ = await _user(db_session)
    end = int((datetime.now(UTC) + timedelta(days=15)).timestamp())
    await _post(client, _event("customer.subscription.created", evt_id="evt_c", sub_id="sub_S5",
                               user_id=user.id, current_period_end=end))
    resp = await _post(client, _event("customer.subscription.deleted", evt_id="evt_d",
                                      sub_id="sub_S5", user_id=user.id, status="canceled"))
    assert resp.json()["disposition"] == "cancelled"
    row = (await db_session.execute(
        select(Subscription).where(Subscription.gateway_sub_id == "sub_S5")
    )).scalar_one()
    assert row.status == "cancelled"
    refreshed = await db_session.get(User, user.id)
    assert refreshed.subscription_tier == "premium"


async def test_webhook_unresolvable_metadata_ignored(client, db_session, stripe_configured):
    resp = await _post(client, _event("customer.subscription.created", evt_id="evt_x",
                                      sub_id="sub_S6", metadata={}))
    assert resp.status_code == 200
    assert resp.json()["disposition"] == "unresolved"
