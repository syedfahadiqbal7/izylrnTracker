"""School-admin password reset (Sprint 9 Slice 1) — the deferred Sprint-8 D2.

Forgot-password → single-use, 30-min, hashed-at-rest token in Redis → reset. Applies to
active `SchoolAdmin`s (both admin + staff; the bootstrap seed secret has no password).

Security:
  * Anti-enumeration — `forgot_password` never reveals whether the email exists; the
    endpoint always returns the same generic 200.
  * Rate-limited per email + per IP (Redis), bumped BEFORE the account lookup so timing
    can't leak existence.
  * Only the SHA-256 of the token is stored (keyed `pwreset:{hash}` → admin id); the raw
    token rides only in the emailed link. Single-use (deleted on redeem) + TTL expiry.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.errors import APIException
from app.core.security import hash_secret
from app.models.school import SchoolAdmin
from app.services.email_gateway import EmailGateway

logger = logging.getLogger("izysafe.pwreset")

_TOKEN_BYTES = 32


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PasswordResetService:
    def __init__(self, db: AsyncSession, redis: Redis, email: EmailGateway) -> None:
        self.db = db
        self.redis = redis
        self.email = email

    async def forgot_password(self, email: str, ip: str | None) -> None:
        """Issue a reset token + email it, if the email maps to an active admin. Always
        silent about existence (the endpoint returns a fixed generic 200)."""
        email = email.lower()
        await self._rate_limit(email, ip)  # before lookup — no timing leak

        admin = (
            await self.db.execute(
                select(SchoolAdmin).where(
                    SchoolAdmin.email == email, SchoolAdmin.active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if admin is None:
            return  # anti-enumeration: do nothing, same outward response

        raw = secrets.token_urlsafe(_TOKEN_BYTES)
        await self.redis.set(
            rk.pwreset_token(_hash_token(raw)), str(admin.id),
            ex=settings.pwreset_token_ttl_minutes * 60,
        )
        link = f"{settings.pwreset_base_url}?token={raw}"
        mins = settings.pwreset_token_ttl_minutes
        text = (
            f"Hi {admin.name or 'there'},\n\n"
            f"We received a request to reset your IzySafe school-admin password.\n"
            f"Reset it here (valid for {mins} minutes):\n{link}\n\n"
            f"If you didn't request this, you can ignore this email."
        )
        html = (
            f"<p>Hi {admin.name or 'there'},</p>"
            f"<p>We received a request to reset your IzySafe school-admin password.</p>"
            f'<p><a href="{link}">Reset your password</a> (valid for {mins} minutes).</p>'
            f"<p>If you didn't request this, you can ignore this email.</p>"
        )
        await self.email.send(admin.email, "Reset your IzySafe school password", text, html)
        logger.info("Password-reset email dispatched for admin %s", admin.id)

    async def reset_password(self, token: str, new_password: str) -> None:
        """Redeem a reset token (single-use) and set the new password."""
        key = rk.pwreset_token(_hash_token(token))
        admin_id = await self.redis.get(key)
        if admin_id is None:
            raise APIException(400, "INVALID_RESET_TOKEN", "This reset link is invalid or has expired")
        await self.redis.delete(key)  # single-use — consume before mutating

        admin = (
            await self.db.execute(
                select(SchoolAdmin).where(
                    SchoolAdmin.id == uuid.UUID(admin_id), SchoolAdmin.active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if admin is None:
            raise APIException(400, "INVALID_RESET_TOKEN", "This reset link is invalid or has expired")

        admin.password_hash = hash_secret(new_password)
        await self.db.commit()
        logger.info("Password reset completed for admin %s", admin.id)

    async def _rate_limit(self, email: str, ip: str | None) -> None:
        await self._bump_or_raise(
            rk.pwreset_rate_email(email), settings.pwreset_rate_per_email,
            "Too many reset requests — please wait and try again later",
        )
        if ip:
            await self._bump_or_raise(
                rk.pwreset_rate_ip(ip), settings.pwreset_rate_per_ip,
                "Too many requests from this device — please wait and try again later",
            )

    async def _bump_or_raise(self, key: str, limit: int, message: str) -> None:
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, settings.pwreset_rate_window_seconds)
        except RedisError:
            return  # fail-open on the limiter — a Redis blip shouldn't block resets
        if count > limit:
            raise APIException(429, "TOO_MANY_REQUESTS", message)
