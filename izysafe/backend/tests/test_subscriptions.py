"""Tests for Subscription core (Sprint 6 Slice 1): plan catalog + current state."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import create_access_token
from app.models.user import Subscription, User

PLANS = "/api/v1/subscriptions/plans"
ME = "/api/v1/subscriptions/me"


async def _user(db, *, country="+91", tier="free", expires=None):
    u = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code=country,
        subscription_tier=tier, subscription_expires_at=expires,
    )
    db.add(u)
    await db.flush()
    return u, {"Authorization": f"Bearer {create_access_token(str(u.id))}"}


# --------------------------------------------------------------------------- #
# Plans
# --------------------------------------------------------------------------- #
async def test_plans_requires_auth(client):
    resp = await client.get(PLANS)
    assert resp.status_code == 401


async def test_plans_inr_for_india(client, db_session):
    _, headers = await _user(db_session, country="+91")
    resp = await client.get(PLANS, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["currency"] == "INR"
    plans = {p["tier"]: p for p in body["data"]}
    assert [p["tier"] for p in body["data"]] == ["free", "basic", "premium", "school"]
    assert plans["free"]["price"] == 0
    assert plans["basic"]["price"] == 99
    assert plans["premium"]["price"] == 199
    assert plans["school"]["price"] is None  # contact sales
    assert plans["basic"]["purchasable"] is True
    assert plans["premium"]["purchasable"] is True
    assert plans["free"]["purchasable"] is False
    assert plans["school"]["purchasable"] is False


async def test_plans_aed_for_uae(client, db_session):
    _, headers = await _user(db_session, country="+971")
    resp = await client.get(PLANS, headers=headers)
    body = resp.json()
    assert body["meta"]["currency"] == "AED"
    plans = {p["tier"]: p for p in body["data"]}
    assert plans["basic"]["price"] == 9
    assert plans["premium"]["price"] == 19


async def test_plan_limits_present(client, db_session):
    _, headers = await _user(db_session)
    plans = {p["tier"]: p for p in (await client.get(PLANS, headers=headers)).json()["data"]}
    assert plans["premium"]["limits"]["children"] is None  # unlimited
    assert plans["basic"]["limits"]["geofences"] == 5


# --------------------------------------------------------------------------- #
# Current subscription (/me)
# --------------------------------------------------------------------------- #
async def test_me_free_user_no_subscription(client, db_session):
    _, headers = await _user(db_session, tier="free")
    resp = await client.get(ME, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tier"] == "free"
    assert data["status"] == "free"
    assert data["is_active_paid"] is False
    assert data["gateway"] is None
    assert data["current_period_end"] is None


async def test_me_active_premium(client, db_session):
    future = datetime.now(UTC) + timedelta(days=20)
    user, headers = await _user(db_session, tier="premium", expires=future)
    db_session.add(Subscription(
        user_id=user.id, tier="premium", gateway="razorpay",
        status="active", expires_at=future,
    ))
    await db_session.flush()
    data = (await client.get(ME, headers=headers)).json()["data"]
    assert data["tier"] == "premium"
    assert data["status"] == "active"
    assert data["is_active_paid"] is True
    assert data["gateway"] == "razorpay"
    assert data["current_period_end"] is not None


async def test_me_lapsed_premium_reads_as_free(client, db_session):
    # A paid tier whose expiry has passed is gated as free (effective_tier), even though
    # the subscription row still says 'active' → the app shows a renew prompt.
    past = datetime.now(UTC) - timedelta(days=2)
    user, headers = await _user(db_session, tier="premium", expires=past)
    db_session.add(Subscription(
        user_id=user.id, tier="premium", gateway="razorpay",
        status="active", expires_at=past,
    ))
    await db_session.flush()
    data = (await client.get(ME, headers=headers)).json()["data"]
    assert data["tier"] == "free"           # effective tier
    assert data["is_active_paid"] is False
    assert data["status"] == "active"       # raw row status preserved


async def test_me_returns_latest_subscription(client, db_session):
    future = datetime.now(UTC) + timedelta(days=20)
    user, headers = await _user(db_session, tier="premium", expires=future)
    db_session.add(Subscription(
        user_id=user.id, tier="basic", gateway="razorpay", status="expired",
        starts_at=datetime.now(UTC) - timedelta(days=60),
        expires_at=datetime.now(UTC) - timedelta(days=30),
    ))
    db_session.add(Subscription(
        user_id=user.id, tier="premium", gateway="stripe", status="active",
        starts_at=datetime.now(UTC) - timedelta(days=5), expires_at=future,
    ))
    await db_session.flush()
    data = (await client.get(ME, headers=headers)).json()["data"]
    assert data["status"] == "active"
    assert data["gateway"] == "stripe"  # newest by starts_at


# --------------------------------------------------------------------------- #
# Drift guard — display catalog vs enforcement constants
# --------------------------------------------------------------------------- #
def test_catalog_limits_match_enforcement_constants():
    from app.core.plans import PLANS as CATALOG
    from app.services.children_service import CHILD_LIMITS
    from app.services.device_service import DEVICE_LIMITS
    from app.services.geofence_service import GEOFENCE_LIMITS
    from app.services.invite_service import GUARDIAN_LIMITS

    for tier in ("free", "basic", "premium", "school"):
        assert CATALOG[tier].limits["children"] == CHILD_LIMITS[tier]
        assert CATALOG[tier].limits["devices_per_child"] == DEVICE_LIMITS[tier]
        assert CATALOG[tier].limits["geofences"] == GEOFENCE_LIMITS[tier]
        assert CATALOG[tier].limits["guardians"] == GUARDIAN_LIMITS[tier]
