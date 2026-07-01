"""Razorpay gateway — India payments (Sprint 6 Slice 2).

Isolates the two real Razorpay touchpoints so the service layer stays testable (a fake
is swapped in via a FastAPI dependency, like TraccarGateway / OtpGateway):

  * `create_subscription` — POST /v1/subscriptions against a recurring Plan ID (Decision C:
    native gateway product). `notes` carries our `{user_id, tier}` so the webhook can
    resolve the payer statelessly — no local pending row (our `subscriptions.status`
    CHECK has no 'created' state, and activation is webhook-driven anyway, Decision D).
  * `verify_webhook` — constant-time HMAC-SHA256 check of the raw body against the
    `X-Razorpay-Signature` header (pure, no network).

`create_subscription` never raises — returns None on any failure so the checkout endpoint
maps it to a clean 502.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("izysafe.razorpay")

_BASE = "https://api.razorpay.com/v1"


class RazorpayGateway:
    async def create_subscription(
        self, plan_id: str, notes: dict[str, str], total_count: int
    ) -> dict[str, Any] | None:
        """Create a recurring subscription; returns Razorpay's subscription object
        (id, short_url, status, ...) or None on failure."""
        if not (settings.razorpay_key_id and settings.razorpay_key_secret):
            logger.warning("Razorpay not configured — cannot create subscription")
            return None
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{_BASE}/subscriptions",
                    auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                    json={
                        "plan_id": plan_id,
                        "total_count": total_count,
                        "customer_notify": 1,
                        "notes": notes,
                    },
                )
        except httpx.HTTPError:
            logger.exception("Razorpay create_subscription failed")
            return None
        if resp.status_code >= 300:
            logger.warning(
                "Razorpay subscription create rejected (HTTP %s): %s",
                resp.status_code, resp.text[:200],
            )
            return None
        return resp.json()

    @staticmethod
    def verify_webhook(body: bytes, signature: str | None) -> bool:
        """Constant-time HMAC-SHA256 verification of a Razorpay webhook body."""
        secret = settings.razorpay_webhook_secret
        if not secret or not signature:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
