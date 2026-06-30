"""Firebase Admin SDK initialization + availability.

Initialization is fault-tolerant: importing this module must NOT crash when the
service-account JSON is absent (tests, or any env without Firebase configured).
The actual Realtime DB writes live in `services/realtime_gateway.py` (and FCM in
a later slice), both of which short-circuit when `is_ready()` is False.
"""
from __future__ import annotations

import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)

_initialized = False


def is_ready() -> bool:
    """True once the Admin SDK has been initialized with valid credentials."""
    return _initialized


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
    except Exception:  # pragma: no cover - exercised only with real creds
        logger.exception("Failed to initialize Firebase Admin.")
        return False
