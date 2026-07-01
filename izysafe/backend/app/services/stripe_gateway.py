"""Stripe gateway — UAE payments (Sprint 6 Slice 3).

Mirrors RazorpayGateway: the two real Stripe touchpoints, isolated + faked in tests.

  * `create_checkout_session` — POST /v1/checkout/sessions in `subscription` mode against
    a recurring Price ID. Our `{user_id, tier}` is stamped onto `subscription_data.metadata`
    so it rides onto the created Subscription object and every `customer.subscription.*`
    event — the webhook resolves the payer statelessly (same pattern as Razorpay's notes).
  * `verify_webhook` — constant-time check of the `Stripe-Signature` header: HMAC-SHA256
    of `"{t}.{body}"`. `t` is part of the signed payload so it can't be forged; replay is
    handled by event-id idempotency in the webhook service (no wall-clock dependency here).

Stripe's API is form-encoded (not JSON). `create_checkout_session` never raises → None on
failure so the checkout endpoint maps it to a clean 502.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("izysafe.stripe")

_BASE = "https://api.stripe.com/v1"


class StripeGateway:
    async def create_checkout_session(
        self, price_id: str, metadata: dict[str, str], success_url: str, cancel_url: str
    ) -> dict[str, Any] | None:
        """Create a subscription-mode Checkout Session; returns Stripe's session object
        (id, url, status, ...) or None on failure."""
        if not settings.stripe_secret_key:
            logger.warning("Stripe not configured — cannot create checkout session")
            return None
        data = {
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata[user_id]": metadata["user_id"],
            "metadata[tier]": metadata["tier"],
            "subscription_data[metadata][user_id]": metadata["user_id"],
            "subscription_data[metadata][tier]": metadata["tier"],
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{_BASE}/checkout/sessions",
                    auth=(settings.stripe_secret_key, ""),
                    data=data,
                )
        except httpx.HTTPError:
            logger.exception("Stripe create_checkout_session failed")
            return None
        if resp.status_code >= 300:
            logger.warning(
                "Stripe checkout session rejected (HTTP %s): %s",
                resp.status_code, resp.text[:200],
            )
            return None
        return resp.json()

    @staticmethod
    def verify_webhook(body: bytes, sig_header: str | None) -> bool:
        """Constant-time HMAC-SHA256 verification of a Stripe webhook (Stripe-Signature
        header 't=...,v1=...'). Signs '{t}.{body}' with the webhook secret."""
        secret = settings.stripe_webhook_secret
        if not secret or not sig_header:
            return False
        parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
        timestamp, signature = parts.get("t"), parts.get("v1")
        if not timestamp or not signature:
            return False
        signed_payload = (timestamp + ".").encode() + body
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
