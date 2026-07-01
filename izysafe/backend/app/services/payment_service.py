"""Payment orchestration (Sprint 6): checkout routing + gateway-webhook application.

`PaymentService.create_checkout` routes to the gateway for the user's country (Decision A:
India → Razorpay, UAE → Stripe) and starts a recurring subscription; the tier is NOT
granted here — only the signature-verified webhook grants it (Decision D).

`SubscriptionWebhookService.apply_razorpay` is the single writer of subscription state:
it resolves the payer from the subscription `notes`, and on activation/renewal upserts the
local `subscriptions` row + flips `users.subscription_tier`/`subscription_expires_at` to
the gateway's `current_end`. Cancellation/halt update the row's status only — the user
keeps access until expiry (the Slice-4 sweep downgrades lapsed users; non-destructive,
Decision E). Idempotent per webhook event id so gateway retries don't double-fire alerts.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.errors import APIException
from app.models.user import Subscription, User
from app.services.alert_service import AlertService
from app.services.fcm_gateway import FcmGateway
from app.services.razorpay_gateway import RazorpayGateway

logger = logging.getLogger("izysafe.payments")

PURCHASABLE_TIERS = {"basic", "premium"}
GATEWAY_EVENT_TTL = 86_400          # 24h idempotency window for webhook event ids
_DEFAULT_PERIOD_DAYS = 30           # fallback period when the gateway omits current_end


def gateway_for_country(country_code: str | None) -> str:
    """India → Razorpay, UAE → Stripe (Decision A). Defaults to Razorpay."""
    return "stripe" if country_code == "+971" else "razorpay"


def _razorpay_plan_id(tier: str) -> str:
    return {"basic": settings.razorpay_plan_basic, "premium": settings.razorpay_plan_premium}[tier]


class PaymentService:
    def __init__(self, db: AsyncSession, razorpay: RazorpayGateway) -> None:
        self.db = db
        self.razorpay = razorpay

    async def create_checkout(self, user: User, tier: str) -> dict[str, Any]:
        """Start a recurring subscription with the user's gateway; return the params the
        app needs to open checkout. Does not grant the tier (webhook does)."""
        if tier not in PURCHASABLE_TIERS:
            raise APIException(400, "INVALID_PLAN", "That plan can't be purchased")

        gateway = gateway_for_country(user.country_code)
        if gateway != "razorpay":
            # Stripe (UAE) lands in Slice 3.
            raise APIException(
                400, "GATEWAY_UNAVAILABLE", "Card payments for your region are coming soon"
            )
        if not _razorpay_plan_id(tier):
            raise APIException(503, "PLAN_NOT_CONFIGURED", "This plan isn't available yet")

        sub = await self.razorpay.create_subscription(
            _razorpay_plan_id(tier),
            {"user_id": str(user.id), "tier": tier},
            settings.subscription_total_count,
        )
        if sub is None:
            raise APIException(502, "CHECKOUT_FAILED", "Couldn't start checkout — please try again")
        return {
            "gateway": "razorpay",
            "subscription_id": sub["id"],
            "short_url": sub.get("short_url"),
            "key_id": settings.razorpay_key_id,
            "status": sub.get("status"),
        }


class SubscriptionWebhookService:
    ACTIVATE_EVENTS = {"subscription.activated", "subscription.charged", "subscription.resumed"}
    CANCEL_EVENTS = {"subscription.cancelled", "subscription.completed"}
    HALT_EVENTS = {"subscription.halted", "subscription.pending"}

    def __init__(self, db: AsyncSession, redis: Redis, fcm: FcmGateway) -> None:
        self.db = db
        self.redis = redis
        self.fcm = fcm

    async def apply_razorpay(self, event: str, event_id: str | None, entity: dict[str, Any]) -> str:
        """Apply one Razorpay subscription webhook event. Returns a short disposition
        string (for logging/tests). Idempotent per event id."""
        if event_id:
            first = await self.redis.set(
                rk.gateway_event("razorpay", event_id), "1", nx=True, ex=GATEWAY_EVENT_TTL
            )
            if not first:
                return "duplicate"

        notes = entity.get("notes") or {}
        user_id, tier = notes.get("user_id"), notes.get("tier")
        sub_id = entity.get("id")
        if not user_id or not tier or not sub_id:
            return "unresolved"  # can't map to a user — ack and drop

        try:
            user = await self.db.get(User, uuid.UUID(str(user_id)))
        except ValueError:
            return "unresolved"
        if user is None or user.deleted_at is not None:
            return "unresolved"

        if event in self.ACTIVATE_EVENTS:
            expires = _epoch_to_dt(entity.get("current_end")) or (
                datetime.now(UTC) + timedelta(days=_DEFAULT_PERIOD_DAYS)
            )
            await self._activate(user, tier, sub_id, expires)
            disposition = "activated"
        elif event in self.CANCEL_EVENTS:
            await self._mark_status(sub_id, "cancelled")
            disposition = "cancelled"
        elif event in self.HALT_EVENTS:
            await self._mark_status(sub_id, "past_due")
            disposition = "past_due"
        else:
            return "ignored"

        await self.db.commit()
        return disposition

    async def _activate(
        self, user: User, tier: str, sub_id: str, expires: datetime
    ) -> None:
        row = (
            await self.db.execute(
                select(Subscription).where(Subscription.gateway_sub_id == sub_id)
            )
        ).scalar_one_or_none()
        if row is None:
            row = Subscription(
                user_id=user.id, tier=tier, gateway="razorpay",
                gateway_sub_id=sub_id, status="active", expires_at=expires,
            )
            self.db.add(row)
        else:
            row.status, row.tier, row.expires_at = "active", tier, expires

        # The user row is the gating source of truth (effective_tier reads it).
        user.subscription_tier = tier
        user.subscription_expires_at = expires
        await AlertService(self.db, self.fcm).notify_user(
            user.id, "system", "Subscription active",
            f"Your {tier.title()} plan is now active.", data={"kind": "subscription", "tier": tier},
        )
        logger.info("Razorpay subscription %s active for user %s (%s)", sub_id, user.id, tier)

    async def _mark_status(self, sub_id: str, status: str) -> None:
        """Update the local row's lifecycle status without touching the user's tier —
        access is retained until expiry (Decision E); the Slice-4 sweep downgrades."""
        row = (
            await self.db.execute(
                select(Subscription).where(Subscription.gateway_sub_id == sub_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            row.status = status
            logger.info("Razorpay subscription %s → %s", sub_id, status)


def _epoch_to_dt(epoch: int | None) -> datetime | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(int(epoch), UTC)
