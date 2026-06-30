"""FCM push gateway — multicast notifications to a family's devices.

Mirrors RealtimeGateway: synchronous firebase-admin wrapped in `asyncio.to_thread`,
never raises (returns the success count, 0 when Firebase is down / no tokens), so a
push failure never breaks alert evaluation. Used by AlertService for every alert
type (device offline this slice; battery/speed/geofence in later slices).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core import firebase as fb

logger = logging.getLogger("izysafe.fcm")


class FcmGateway:
    """Default production gateway. Construct once per use (cheap)."""

    async def send(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        urgent: bool = False,
    ) -> int:
        """Send a multicast push. Returns the number of successful deliveries.

        urgent=True marks the message MAX priority on a dedicated 'sos' channel and
        bypasses DND/quiet hours (Android high priority + APNS critical interruption)
        — used for SOS, which always overrides School Mode (Flow C, Decision C)."""
        if not tokens or not fb.is_ready():
            if tokens:
                logger.warning("Firebase not initialized — skipping FCM to %d tokens", len(tokens))
            return 0
        try:
            return await asyncio.to_thread(
                self._send_multicast, tokens, title, body, data or {}, urgent
            )
        except Exception:
            logger.exception("FCM send failed for %d tokens", len(tokens))
            return 0

    @staticmethod
    def _send_multicast(
        tokens: list[str], title: str, body: str, data: dict[str, Any], urgent: bool
    ) -> int:
        from firebase_admin import messaging

        android = apns = None
        if urgent:
            android = messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="sos", priority="max", sound="default"
                ),
            )
            apns = messaging.APNSConfig(
                headers={"apns-priority": "10"},
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", content_available=True)
                ),
            )

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            # FCM data values must be strings.
            data={k: str(v) for k, v in data.items()},
            android=android,
            apns=apns,
        )
        resp = messaging.send_each_for_multicast(message)
        return resp.success_count
