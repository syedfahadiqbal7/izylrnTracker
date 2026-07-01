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


class SubscriptionMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tier: str                    # effective tier (expiry-aware) — the one gates actually use
    status: str                  # 'active' | 'past_due' | 'cancelled' | 'expired' | 'free'
    is_active_paid: bool
    gateway: str | None
    current_period_end: datetime | None
