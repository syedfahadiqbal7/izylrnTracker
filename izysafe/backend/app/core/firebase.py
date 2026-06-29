"""Firebase Admin SDK wrapper (STUB — wired up in Sprint 2).

Initialization is lazy and fault-tolerant: importing this module must NOT crash
when the service-account JSON is absent (e.g. during Sprint 0 / Sprint 1 tests).
Real Realtime DB writes + FCM sends are implemented in Sprint 2.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_initialized = False


def init_firebase() -> bool:
    """Initialize the Firebase Admin app once. Returns True if ready.

    No-ops gracefully (logs a warning) if credentials are missing so the rest of
    the app keeps working in environments without Firebase configured.
    """
    global _initialized
    if _initialized:
        return True

    cred_path = settings.firebase_credentials_json
    if not cred_path or not os.path.exists(cred_path):
        logger.warning("Firebase credentials not found at %s — Firebase disabled.", cred_path)
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {"databaseURL": settings.firebase_database_url})
        _initialized = True
        logger.info("Firebase Admin initialized.")
        return True
    except Exception:  # pragma: no cover - exercised in Sprint 2
        logger.exception("Failed to initialize Firebase Admin.")
        return False


# --- Realtime DB / FCM helpers are implemented in Sprint 2 -------------------
def update_live_location(child_id: str, payload: dict[str, Any]) -> None:
    """Write live_locations/{child_id}/latest. Implemented in Sprint 2."""
    raise NotImplementedError("Firebase RT DB writes are implemented in Sprint 2.")


def set_sos(child_id: str, payload: dict[str, Any]) -> None:
    """Write sos/{child_id}. Implemented in Sprint 4."""
    raise NotImplementedError("SOS Firebase writes are implemented in Sprint 4.")
