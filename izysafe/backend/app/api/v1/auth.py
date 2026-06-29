"""Auth endpoints (Sprint 1). This slice: POST /auth/send-otp."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_otp_gateway
from app.core.database import get_db
from app.core.errors import success
from app.core.redis import get_redis
from app.schemas.auth import SendOtpRequest, VerifyOtpRequest
from app.services.otp_gateway import OtpGateway
from app.services.otp_service import OtpService

router = APIRouter(prefix="/auth", tags=["auth"])


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
    result = await service.send_otp(payload.phone, client_ip)
    return success(result)


@router.post("/verify-otp")
async def verify_otp(
    payload: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    gateway: OtpGateway = Depends(get_otp_gateway),
) -> dict:
    """Verify the OTP, create the user if new, and return JWT access+refresh tokens."""
    service = OtpService(db, redis, gateway)
    result = await service.verify_otp(payload.phone, payload.otp)
    return success(result)
