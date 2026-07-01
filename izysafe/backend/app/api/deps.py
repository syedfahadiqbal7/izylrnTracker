"""Shared FastAPI dependencies (gateways + auth).

Gateways are provided via dependencies so tests can override them with fakes.
get_current_auth does the full JWT work (decode → denylist check → user load);
get_current_user is the thin wrapper most endpoints use.
"""
from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.errors import APIException
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.user import User
from app.services.battery_service import BatteryService
from app.services.device_status import DeviceStatusService
from app.services.chat_service import ChatInboundService
from app.services.fcm_gateway import FcmGateway
from app.services.geocoding_gateway import GeocodingGateway
from app.services.geofence_breach_service import GeofenceBreachService
from app.services.route_deviation_service import RouteDeviationService
from app.services.sos_service import SosAlarmService
from app.services.watch_removed_service import WatchRemovedService
from app.services.speed_service import SpeedService
from app.services.invite_gateway import InviteGateway
from app.services.otp_gateway import OtpGateway
from app.services.razorpay_gateway import RazorpayGateway
from app.services.realtime_gateway import RealtimeGateway
from app.services.stripe_gateway import StripeGateway
from app.services.token_service import is_denylisted
from app.services.traccar_gateway import TraccarGateway

_bearer = HTTPBearer(auto_error=False)


def get_otp_gateway() -> OtpGateway:
    return OtpGateway()


def get_invite_gateway() -> InviteGateway:
    return InviteGateway()


def get_realtime_gateway() -> RealtimeGateway:
    return RealtimeGateway()


def get_fcm_gateway() -> FcmGateway:
    return FcmGateway()


def get_traccar_gateway() -> TraccarGateway:
    return TraccarGateway()


def get_geocoding_gateway() -> GeocodingGateway:
    return GeocodingGateway()


def get_razorpay_gateway() -> RazorpayGateway:
    return RazorpayGateway()


def get_stripe_gateway() -> StripeGateway:
    return StripeGateway()


def get_device_status_service(
    redis: Redis = Depends(get_redis),
) -> DeviceStatusService:
    # Uses its own session factory (BackgroundTask runs after the request session closes).
    return DeviceStatusService(AsyncSessionLocal, redis)


def get_battery_service(
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> BatteryService:
    # BackgroundTask → own session factory (the request session is gone by then).
    return BatteryService(AsyncSessionLocal, redis, fcm)


def get_speed_service(
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> SpeedService:
    return SpeedService(AsyncSessionLocal, redis, fcm)


def get_geofence_breach_service(
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> GeofenceBreachService:
    # BackgroundTask → own session factory (the request session is gone by then).
    return GeofenceBreachService(AsyncSessionLocal, redis, fcm)


def get_route_deviation_service(
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> RouteDeviationService:
    # BackgroundTask → own session factory (the request session is gone by then).
    return RouteDeviationService(AsyncSessionLocal, redis, fcm)


def get_sos_alarm_service(
    redis: Redis = Depends(get_redis),
    realtime: RealtimeGateway = Depends(get_realtime_gateway),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> SosAlarmService:
    # BackgroundTask → own session factory (the request session is gone by then).
    return SosAlarmService(AsyncSessionLocal, redis, realtime, fcm)


def get_watch_removed_service(
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> WatchRemovedService:
    # BackgroundTask → own session factory (the request session is gone by then).
    return WatchRemovedService(AsyncSessionLocal, redis, fcm)


def get_chat_inbound_service(
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> ChatInboundService:
    # BackgroundTask → own session factory (the request session is gone by then).
    return ChatInboundService(AsyncSessionLocal, fcm)


async def verify_traccar_secret(
    x_traccar_secret: str | None = Header(default=None, alias="X-Traccar-Secret"),
) -> None:
    """Authenticate Traccar webhooks via the shared static secret header.

    Traccar's JSON forwarder can only send a fixed header (it cannot HMAC-sign the
    body), so we constant-time compare the secret and rely on network trust — the
    backend is not publicly reachable, only Traccar can hit it (CLAUDE.md §7).
    """
    expected = settings.traccar_webhook_secret
    if not x_traccar_secret or not hmac.compare_digest(x_traccar_secret, expected):
        raise APIException(401, "WEBHOOK_UNAUTHORIZED", "Invalid webhook secret")


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
