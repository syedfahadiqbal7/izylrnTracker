"""Subscription read service (Sprint 6 Slice 1).

Request-path reads for the paywall + account screen: the plan catalog priced in the
user's currency, and the user's current subscription state. The tier that gates actually
enforce is ``effective_tier`` (a lapsed paid tier reads as free) — this service surfaces
that same effective tier alongside the raw subscription row so the app can show renew /
past-due states. Checkout + the gateway webhooks that WRITE subscriptions land in Slices
2–3.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import plans as plan_catalog
from app.models.user import Subscription, User
from app.services.children_service import effective_tier


class SubscriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def list_plans(self, user: User) -> tuple[str, list[dict[str, Any]]]:
        """The plan catalog priced in the user's currency (INR/AED by country).
        Returns (currency, [plan dict, ...]) in tier order."""
        currency = plan_catalog.currency_for_country(user.country_code)
        rows = [
            {
                "tier": p.tier,
                "name": p.name,
                "currency": currency,
                "price": p.price_for(currency),
                "purchasable": p.purchasable,
                "billing_period": p.billing_period,
                "features": p.features,
                "limits": p.limits,
            }
            for p in (plan_catalog.PLANS[t] for t in plan_catalog.TIER_ORDER)
        ]
        return currency, rows

    async def get_current(self, user: User) -> dict[str, Any]:
        """The user's current subscription state. `tier` is the effective (expiry-aware)
        tier the gates use; `status` comes from the latest subscription row, or 'free'
        when the user has never subscribed."""
        tier = effective_tier(user)
        # is_active_paid tracks the EFFECTIVE tier (what the gates actually grant), so it
        # stays consistent with `tier` whether or not a subscription row exists yet.
        is_active_paid = tier != "free"
        sub = (
            await self.db.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .order_by(Subscription.starts_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if sub is None:
            return {
                "tier": tier,
                "status": "free",
                "is_active_paid": is_active_paid,
                "gateway": None,
                "current_period_end": None,
            }
        return {
            "tier": tier,
            "status": sub.status,
            "is_active_paid": is_active_paid,
            "gateway": sub.gateway,
            "current_period_end": sub.expires_at,
        }
