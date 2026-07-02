"""Security primitives: bcrypt hashing (OTP/passwords) + JWT (HS256) tokens.

All conventions per CLAUDE.md §7:
  * JWT HS256, access 24h / refresh 30d.
  * OTP stored only as a bcrypt hash, never plaintext.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


# --------------------------------------------------------------------------- #
# bcrypt hashing (OTP codes + school-admin passwords)
# --------------------------------------------------------------------------- #
def hash_secret(plain: str) -> str:
    """bcrypt-hash a short secret (OTP code or password). Returns utf-8 string."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_secret(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt verify. Never raises on a bad hash — returns False."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# JWT (HS256)
# --------------------------------------------------------------------------- #
def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta,
                  extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, extra: dict[str, Any] | None = None) -> str:
    return _create_token(
        user_id, "access", timedelta(minutes=settings.jwt_access_expire_minutes), extra
    )


def create_refresh_token(user_id: str, extra: dict[str, Any] | None = None) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=settings.jwt_refresh_expire_days), extra
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode + validate a JWT. Raises jwt.PyJWTError subclasses on failure;
    raises ValueError if the token type doesn't match expected_type."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if expected_type is not None and payload.get("type") != expected_type:
        raise ValueError(f"Expected {expected_type} token, got {payload.get('type')}")
    return payload
