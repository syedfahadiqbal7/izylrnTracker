"""Shared FastAPI dependencies (gateways + auth).

Gateways are provided via dependencies so tests can override them with fakes.
get_current_auth does the full JWT work (decode → denylist check → user load);
get_current_user is the thin wrapper most endpoints use.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import APIException
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.user import User
from app.services.otp_gateway import OtpGateway
from app.services.token_service import is_denylisted

_bearer = HTTPBearer(auto_error=False)


def get_otp_gateway() -> OtpGateway:
    return OtpGateway()


@dataclass
class AuthContext:
    """Resolved auth state for a request: the user + the verified access claims."""

    user: User
    payload: dict


async def get_current_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AuthContext:
    if credentials is None or not credentials.credentials:
        raise APIException(401, "TOKEN_MISSING", "Authentication required")

    token = credentials.credentials
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.ExpiredSignatureError:
        raise APIException(401, "TOKEN_EXPIRED", "Session expired — please log in again")
    except (jwt.PyJWTError, ValueError):
        raise APIException(401, "TOKEN_INVALID", "Invalid authentication token")

    # Denylist check — FAIL-OPEN: a Redis blip must not lock out every user.
    jti = payload.get("jti")
    if jti:
        try:
            revoked = await is_denylisted(redis, "access", jti)
        except RedisError:
            revoked = False
        if revoked:
            raise APIException(401, "TOKEN_REVOKED", "Session ended — please log in again")

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError):
        raise APIException(401, "TOKEN_INVALID", "Invalid authentication token")

    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise APIException(401, "USER_NOT_FOUND", "Account not found — please log in again")

    return AuthContext(user=user, payload=payload)


async def get_current_user(auth: AuthContext = Depends(get_current_auth)) -> User:
    return auth.user
