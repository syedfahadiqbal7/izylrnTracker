"""School / B2B backend services (Sprint 8 Slice 1) — admin auth + school profile.

School admins are a SEPARATE identity from parents (CLAUDE.md §7): email + password
(bcrypt), their own JWTs carrying a ``scope="school_admin"`` claim so a parent token can
never reach a school endpoint (and vice-versa — an admin's `sub` isn't a `users` row).
The JWT/denylist plumbing is reused from the parent auth stack.

  * ``SchoolAuthService`` — env-gated bootstrap (seed a school + first admin), login
    (with a per-email brute-force guard), refresh rotation, logout, staff invite,
    admin listing. Privileged ops (invite, config write) require role='admin'.
  * ``SchoolService`` — the admin's own school profile + attendance-threshold config.
"""
from __future__ import annotations

import hmac
import logging
import uuid
from typing import Any

import jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.errors import APIException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_secret,
    verify_secret,
)
from app.models.school import School, SchoolAdmin
from app.services.token_service import denylist, is_denylisted

logger = logging.getLogger("izysafe.school")

SCHOOL_ADMIN_SCOPE = "school_admin"
_REDIS_DOWN = APIException(503, "AUTH_BACKEND_UNAVAILABLE", "Please try again in a moment")


class SchoolAuthService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis

    # --------------------------------------------------------------- bootstrap
    async def seed(self, data: dict[str, Any]) -> tuple[School, SchoolAdmin]:
        """Env-gated provisioning of a school + its first admin (Decision D1)."""
        expected = settings.school_seed_secret
        if not expected:
            raise APIException(403, "SEED_DISABLED", "School seeding is disabled")
        if not hmac.compare_digest(data.get("secret", ""), expected):
            raise APIException(403, "SEED_FORBIDDEN", "Invalid seed secret")

        email = data["admin_email"].lower()
        await self._ensure_email_free(email)

        school = School(name=data["school_name"], timezone=data.get("timezone", "Asia/Kolkata"))
        self.db.add(school)
        await self.db.flush()
        admin = SchoolAdmin(
            school_id=school.id, email=email,
            password_hash=hash_secret(data["admin_password"]),
            name=data.get("admin_name"), role="admin", active=True,
        )
        self.db.add(admin)
        await self.db.commit()
        await self.db.refresh(school)
        await self.db.refresh(admin)
        logger.info("Seeded school %s with admin %s", school.id, admin.id)
        return school, admin

    # ------------------------------------------------------------------- login
    async def login(self, email: str, password: str) -> dict:
        email = email.lower()
        await self._check_login_rate(email)

        admin = (
            await self.db.execute(
                select(SchoolAdmin).where(
                    SchoolAdmin.email == email, SchoolAdmin.active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if admin is None or not verify_secret(password, admin.password_hash):
            await self._bump_login_fail(email)
            raise APIException(401, "INVALID_CREDENTIALS", "Incorrect email or password")

        await self._clear_login_fail(email)
        return self._issue_tokens(admin)

    async def refresh(self, refresh_token: str) -> dict:
        try:
            claims = decode_token(refresh_token, expected_type="refresh")
        except jwt.ExpiredSignatureError:
            raise APIException(401, "TOKEN_EXPIRED", "Session expired — please log in again")
        except (jwt.PyJWTError, ValueError):
            raise APIException(401, "TOKEN_INVALID", "Invalid refresh token")
        if claims.get("scope") != SCHOOL_ADMIN_SCOPE:
            raise APIException(401, "TOKEN_INVALID", "Invalid refresh token")

        jti = claims.get("jti")
        if jti:
            try:
                if await is_denylisted(self.redis, "refresh", jti):
                    raise APIException(401, "TOKEN_REVOKED", "Session ended — please log in again")
            except RedisError:
                raise _REDIS_DOWN  # fail-closed on refresh

        try:
            admin_id = uuid.UUID(str(claims.get("sub")))
        except (ValueError, TypeError):
            raise APIException(401, "TOKEN_INVALID", "Invalid refresh token")
        admin = (
            await self.db.execute(
                select(SchoolAdmin).where(
                    SchoolAdmin.id == admin_id, SchoolAdmin.active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if admin is None:
            raise APIException(401, "ADMIN_NOT_FOUND", "Account not found — please log in again")

        try:
            if jti:
                await denylist(self.redis, "refresh", jti, claims["exp"])
        except RedisError:
            raise _REDIS_DOWN
        return self._issue_tokens(admin)

    async def logout(self, access_payload: dict, refresh_token: str) -> None:
        refresh_claims: dict | None
        try:
            refresh_claims = decode_token(refresh_token, expected_type="refresh")
        except (jwt.PyJWTError, ValueError):
            refresh_claims = None
        try:
            a_jti, a_exp = access_payload.get("jti"), access_payload.get("exp")
            if a_jti and a_exp:
                await denylist(self.redis, "access", a_jti, a_exp)
            if refresh_claims and refresh_claims.get("jti"):
                await denylist(self.redis, "refresh", refresh_claims["jti"], refresh_claims["exp"])
        except RedisError:
            raise APIException(503, "AUTH_BACKEND_UNAVAILABLE", "Could not log out — please try again")

    # --------------------------------------------------------- admin management
    async def invite_staff(self, admin: SchoolAdmin, data: dict[str, Any]) -> SchoolAdmin:
        self._require_admin(admin)
        email = data["email"].lower()
        await self._ensure_email_free(email)
        new_admin = SchoolAdmin(
            school_id=admin.school_id, email=email,
            password_hash=hash_secret(data["password"]),
            name=data.get("name"), role=data.get("role", "staff"), active=True,
        )
        self.db.add(new_admin)
        await self.db.commit()
        await self.db.refresh(new_admin)
        return new_admin

    async def list_admins(self, admin: SchoolAdmin) -> list[SchoolAdmin]:
        rows = (
            await self.db.execute(
                select(SchoolAdmin)
                .where(SchoolAdmin.school_id == admin.school_id)
                .order_by(SchoolAdmin.created_at)
            )
        ).scalars().all()
        return list(rows)

    # ---------------------------------------------------------------- helpers
    def _issue_tokens(self, admin: SchoolAdmin) -> dict:
        extra = {"scope": SCHOOL_ADMIN_SCOPE}
        return {
            "access_token": create_access_token(str(admin.id), extra=extra),
            "refresh_token": create_refresh_token(str(admin.id), extra=extra),
            "token_type": "bearer",
        }

    @staticmethod
    def _require_admin(admin: SchoolAdmin) -> None:
        if admin.role != "admin":
            raise APIException(403, "FORBIDDEN", "This action requires an admin role")

    async def _ensure_email_free(self, email: str) -> None:
        exists = (
            await self.db.execute(select(SchoolAdmin.id).where(SchoolAdmin.email == email))
        ).first()
        if exists is not None:
            raise APIException(409, "EMAIL_TAKEN", "An admin with this email already exists")

    async def _check_login_rate(self, email: str) -> None:
        try:
            count = await self.redis.get(rk.school_login_rate(email))
        except RedisError:
            return  # fail-open on the rate limiter — never lock out on a Redis blip
        if count is not None and int(count) >= settings.school_login_max_attempts:
            raise APIException(429, "TOO_MANY_ATTEMPTS", "Too many attempts — please try again later")

    async def _bump_login_fail(self, email: str) -> None:
        try:
            key = rk.school_login_rate(email)
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, settings.school_login_window_seconds)
        except RedisError:
            pass

    async def _clear_login_fail(self, email: str) -> None:
        try:
            await self.redis.delete(rk.school_login_rate(email))
        except RedisError:
            pass


class SchoolService:
    """The admin's own school profile + attendance-threshold config."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_school(self, admin: SchoolAdmin) -> School:
        school = (
            await self.db.execute(select(School).where(School.id == admin.school_id))
        ).scalar_one_or_none()
        if school is None:
            raise APIException(404, "SCHOOL_NOT_FOUND", "School not found")
        return school

    async def update_school(self, admin: SchoolAdmin, fields: dict[str, Any]) -> School:
        if admin.role != "admin":
            raise APIException(403, "FORBIDDEN", "This action requires an admin role")
        school = await self.get_school(admin)
        for key, value in fields.items():
            setattr(school, key, value)
        await self.db.commit()
        await self.db.refresh(school)
        return school
