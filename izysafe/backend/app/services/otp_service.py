"""OTP send/verify business logic (Feature 7).

This slice implements send_otp:
  validate phone → rate-limit (phone + IP) → generate 6-digit OTP →
  bcrypt-hash + persist → deliver (WhatsApp, fallback SMS).
verify_otp + token issuance arrive in the next slice.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import APIException
from app.core.security import hash_secret
from app.core.validators import validate_phone
from app.models.user import OtpSession
from app.services.otp_gateway import OtpGateway


class OtpService:
    def __init__(self, db: AsyncSession, redis: Redis, gateway: OtpGateway) -> None:
        self.db = db
        self.redis = redis
        self.gateway = gateway

    # ----------------------------------------------------------------- public
    async def send_otp(self, phone: str, ip: str | None) -> dict:
        phone = validate_phone(phone)
        await self._enforce_rate_limits(phone, ip)

        otp = self._generate_otp()
        channel = await self._deliver(phone, otp)   # raises if all channels fail

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expiry_minutes)
        self.db.add(
            OtpSession(
                phone=phone,
                otp_hash=hash_secret(otp),
                channel=channel,
                expires_at=expires_at,
            )
        )
        await self.db.commit()

        return {
            "success": True,
            "expires_in": settings.otp_expiry_minutes * 60,
            "channel": channel,
        }

    # ---------------------------------------------------------------- helpers
    def _generate_otp(self) -> str:
        return str(secrets.randbelow(10 ** settings.otp_length)).zfill(settings.otp_length)

    async def _enforce_rate_limits(self, phone: str, ip: str | None) -> None:
        await self._bump_or_raise(
            f"rate:otp:{phone}",
            settings.otp_rate_per_phone,
            "RATE_LIMIT_PHONE",
            "Too many OTP requests — please wait and try again in 60 minutes",
        )
        if ip:
            await self._bump_or_raise(
                f"rate:otp:ip:{ip}",
                settings.otp_rate_per_ip,
                "RATE_LIMIT_IP",
                "Too many requests from this device — please wait 60 minutes",
            )

    async def _bump_or_raise(self, key: str, limit: int, code: str, message: str) -> None:
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, settings.otp_rate_window_seconds)
        if count > limit:
            raise APIException(429, code, message)

    async def _deliver(self, phone: str, otp: str) -> str:
        if await self.gateway.send_whatsapp(phone, otp):
            return "whatsapp"
        if await self.gateway.send_sms(phone, otp):
            return "sms"
        raise APIException(
            502, "OTP_SEND_FAILED",
            "Could not send OTP — please verify your phone number is correct and try again",
        )
