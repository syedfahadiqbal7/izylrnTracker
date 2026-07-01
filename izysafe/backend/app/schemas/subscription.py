"""Pydantic schemas for Subscriptions (Sprint 6)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlanResponse(BaseModel):
    tier: str
    name: str
    currency: str
    price: int | None            # monthly price, major units, user's currency (null = custom)
    purchasable: bool
    billing_period: str | None
    features: list[str]
    limits: dict[str, int | None]


class CheckoutRequest(BaseModel):
    tier: str  # 'basic' | 'premium' — validated in the service (business rule → 400)


class CheckoutResponse(BaseModel):
    """Unified across gateways — the app branches on `gateway`.

    Razorpay: `reference_id` = subscription id, `checkout_url` = short_url, `key_id` set
    (in-app SDK). Stripe: `reference_id` = session id, `checkout_url` = hosted page,
    `key_id` null.
    """

    gateway: str
    reference_id: str
    checkout_url: str | None
    key_id: str | None
    status: str | None


class SubscriptionMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tier: str                    # effective tier (expiry-aware) — the one gates actually use
    status: str                  # 'active' | 'past_due' | 'cancelled' | 'expired' | 'free'
    is_active_paid: bool
    gateway: str | None
    current_period_end: datetime | None
