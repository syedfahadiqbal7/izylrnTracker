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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import APIException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_secret,
    verify_secret,
)
from app.core.validators import validate_phone
from app.models.user import OtpSession, User
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

    async def verify_otp(self, phone: str, otp: str) -> dict:
        phone = validate_phone(phone)
        self._validate_otp_format(otp)

        session = await self._latest_unverified_session(phone)
        if session is None or session.expires_at <= datetime.now(timezone.utc):
            raise APIException(400, "OTP_EXPIRED", "OTP has expired — tap Resend to get a new one")

        if session.attempts >= settings.otp_max_attempts:
            raise APIException(
                429, "OTP_MAX_ATTEMPTS",
                "Too many wrong attempts — please request a new OTP",
            )

        if not verify_secret(otp, session.otp_hash):
            session.attempts += 1
            await self.db.commit()
            remaining = settings.otp_max_attempts - session.attempts
            if remaining <= 0:
                raise APIException(
                    429, "OTP_MAX_ATTEMPTS",
                    "Too many wrong attempts — please request a new OTP",
                )
            raise APIException(
                400, "OTP_INVALID", f"Incorrect OTP — {remaining} attempts remaining"
            )

        # Correct OTP → consume the session and (find or) create the user.
        session.verified = True
        user, is_new = await self._get_or_create_user(phone)
        user.last_login_at = datetime.now(timezone.utc)  # stamp parent login (Sprint 10)
        await self.db.commit()

        return {
            "access_token": create_access_token(str(user.id)),
            "refresh_token": create_refresh_token(str(user.id)),
            "token_type": "bearer",
            "is_new_user": is_new,
        }

    # ---------------------------------------------------------------- helpers
    def _validate_otp_format(self, otp: str) -> None:
        if not otp or not otp.isdigit() or len(otp) != settings.otp_length:
            raise APIException(
                400, "OTP_INVALID_FORMAT",
                f"OTP must be exactly {settings.otp_length} digits",
            )

    async def _latest_unverified_session(self, phone: str) -> OtpSession | None:
        result = await self.db.execute(
            select(OtpSession)
            .where(OtpSession.phone == phone, OtpSession.verified.is_(False))
            .order_by(OtpSession.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_user(self, phone: str) -> tuple[User, bool]:
        existing = await self.db.execute(
            select(User).where(User.phone == phone, User.deleted_at.is_(None))
        )
        user = existing.scalar_one_or_none()
        if user is not None:
            return user, False
        user = User(phone=phone, country_code="+971" if phone.startswith("+971") else "+91")
        self.db.add(user)
        await self.db.flush()  # populate user.id for token subject
        return user, True

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
