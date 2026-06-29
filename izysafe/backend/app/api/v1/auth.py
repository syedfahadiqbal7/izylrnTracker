"""Auth endpoints (Sprint 1): send-otp, verify-otp, refresh, logout, me."""
from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Depends, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_auth, get_current_user, get_otp_gateway
from app.core.database import get_db
from app.core.errors import APIException, success
from app.core.redis import get_redis
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.schemas.auth import (
    FcmTokenRequest,
    LogoutRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    SendOtpRequest,
    UserResponse,
    VerifyOtpRequest,
)
from app.services.otp_gateway import OtpGateway
from app.services.otp_service import OtpService
from app.services.token_service import denylist, is_denylisted
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])

_REDIS_DOWN = APIException(
    503, "AUTH_BACKEND_UNAVAILABLE", "Please try again in a moment"
)


@router.post("/send-otp")
async def send_otp(
    payload: SendOtpRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    gateway: OtpGateway = Depends(get_otp_gateway),
) -> dict:
    """Send a 6-digit OTP via WhatsApp (fallback SMS) to an IN/UAE phone."""
    service = OtpService(db, redis, gateway)
    client_ip = request.client.host if request.client else None
    return success(await service.send_otp(payload.phone, client_ip))


@router.post("/verify-otp")
async def verify_otp(
    payload: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    gateway: OtpGateway = Depends(get_otp_gateway),
) -> dict:
    """Verify the OTP, create the user if new, and return JWT access+refresh tokens."""
    service = OtpService(db, redis, gateway)
    return success(await service.verify_otp(payload.phone, payload.otp))


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Rotate a refresh token: validate → reject if revoked → issue a new
    access+refresh pair and denylist the old refresh token."""
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except jwt.ExpiredSignatureError:
        raise APIException(401, "TOKEN_EXPIRED", "Session expired — please log in again")
    except (jwt.PyJWTError, ValueError):
        raise APIException(401, "TOKEN_INVALID", "Invalid refresh token")

    jti = claims.get("jti")
    if jti:
        try:
            revoked = await is_denylisted(redis, "refresh", jti)
        except RedisError:
            raise _REDIS_DOWN          # fail-closed on refresh
        if revoked:
            raise APIException(401, "TOKEN_REVOKED", "Session ended — please log in again")

    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError):
        raise APIException(401, "TOKEN_INVALID", "Invalid refresh token")

    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise APIException(401, "USER_NOT_FOUND", "Account not found — please log in again")

    # Rotate: revoke the presented refresh token, issue a fresh pair.
    try:
        if jti:
            await denylist(redis, "refresh", jti, claims["exp"])
    except RedisError:
        raise _REDIS_DOWN

    return success(
        {
            "access_token": create_access_token(str(user.id)),
            "refresh_token": create_refresh_token(str(user.id)),
            "token_type": "bearer",
        }
    )


@router.delete("/logout")
async def logout(
    payload: LogoutRequest,
    auth: AuthContext = Depends(get_current_auth),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Revoke the current access token and the supplied refresh token."""
    # Refresh token is best-effort: a malformed one still lets us kill the access token.
    refresh_claims: dict | None
    try:
        refresh_claims = decode_token(payload.refresh_token, expected_type="refresh")
    except (jwt.PyJWTError, ValueError):
        refresh_claims = None

    try:
        a_jti, a_exp = auth.payload.get("jti"), auth.payload.get("exp")
        if a_jti and a_exp:
            await denylist(redis, "access", a_jti, a_exp)
        if refresh_claims and refresh_claims.get("jti"):
            await denylist(redis, "refresh", refresh_claims["jti"], refresh_claims["exp"])
    except RedisError:
        raise APIException(
            503, "AUTH_BACKEND_UNAVAILABLE", "Could not log out — please try again"
        )

    return success({"success": True})


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)) -> dict:
    """Return the authenticated user's profile."""
    return success(UserResponse.model_validate(current_user).model_dump(mode="json"))


@router.put("/me")
async def update_me(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Partial profile update (name, email, photo, language, timezone, quiet hours)."""
    user = await UserService(db).update_profile(
        current_user, payload.model_dump(exclude_unset=True)
    )
    return success(UserResponse.model_validate(user).model_dump(mode="json"))


@router.put("/me/fcm-token")
async def set_fcm_token(
    payload: FcmTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register/refresh the device FCM token for push notifications."""
    await UserService(db).set_fcm_token(current_user, payload.fcm_token)
    return success({"success": True})
