"""Firebase Realtime DB gateway — the live-map write of Flow A.

The parent app streams `live_locations/{child_id}/latest`; this gateway writes it.
Mirrors the OtpGateway pattern (tests swap in a fake via dependency override).

firebase-admin is **synchronous**, so every SDK call is wrapped in
`asyncio.to_thread` to avoid blocking the event loop. Calls never raise — they
return True on success, False otherwise (Firebase down / not configured) — so a
Firebase blip never breaks ingestion. The write runs off the hot path in a
FastAPI BackgroundTask (CLAUDE.md §4/§5 Flow A).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core import firebase as fb

logger = logging.getLogger("izysafe.realtime")


class RealtimeGateway:
    """Default production gateway. Construct once per request (cheap)."""

    async def update_live_location(self, child_id: str, payload: dict[str, Any]) -> bool:
        if not fb.is_ready():
            logger.warning("Firebase not initialized — skipping live location for %s", child_id)
            return False
        try:
            await asyncio.to_thread(
                self._set, f"live_locations/{child_id}/latest", payload
            )
            return True
        except Exception:
            logger.exception("Realtime DB write failed for child %s", child_id)
            return False

    @staticmethod
    def _set(path: str, payload: dict[str, Any]) -> None:
        from firebase_admin import db

        db.reference(path).set(payload)
