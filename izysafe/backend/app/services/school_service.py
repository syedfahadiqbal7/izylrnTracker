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
from sqlalchemy import func, select
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

    # --------------------------------------------------------- self-service
    async def change_password(
        self, admin: SchoolAdmin, current_password: str, new_password: str
    ) -> None:
        """Self-service password change for a logged-in admin. Rate-limited per admin;
        the current password must match (400 otherwise). Shares hashing with reset."""
        await self._pwchange_rate_limit(admin.id)
        if not verify_secret(current_password, admin.password_hash):
            raise APIException(400, "CURRENT_PASSWORD_INCORRECT", "Your current password is incorrect")
        admin.password_hash = hash_secret(new_password)
        await self.db.commit()
        await self._clear_pwchange_rate(admin.id)  # a successful change resets the counter
        logger.info("Admin %s changed their password", admin.id)

    async def update_profile(self, admin: SchoolAdmin, fields: dict[str, Any]) -> SchoolAdmin:
        """Update the admin's own non-sensitive fields (currently just `name`)."""
        if "name" in fields and fields["name"] is not None:
            admin.name = fields["name"]
        await self.db.commit()
        await self.db.refresh(admin)
        return admin

    async def list_admins(self, admin: SchoolAdmin) -> list[SchoolAdmin]:
        rows = (
            await self.db.execute(
                select(SchoolAdmin)
                .where(SchoolAdmin.school_id == admin.school_id)
                .order_by(SchoolAdmin.created_at)
            )
        ).scalars().all()
        return list(rows)

    # ----------------------------------------------------- admin management
    async def manage_update(
        self, admin: SchoolAdmin, target_id: uuid.UUID, fields: dict[str, Any]
    ) -> SchoolAdmin:
        """Update another admin's role/name (admin-only). Demoting the last active admin
        to staff is blocked (the school must keep one)."""
        self._require_admin(admin)
        target = await self._load_target(admin, target_id)
        new_role = fields.get("role")
        if new_role == "staff" and target.role == "admin":
            await self._guard_last_admin(target)
        if new_role is not None:
            target.role = new_role
        if fields.get("name") is not None:
            target.name = fields["name"]
        await self.db.commit()
        await self.db.refresh(target)
        return target

    async def set_active(
        self, admin: SchoolAdmin, target_id: uuid.UUID, active: bool
    ) -> SchoolAdmin:
        """Deactivate/reactivate another admin (admin-only). Can't deactivate yourself
        or the last active admin. Deactivation blocks login + existing tokens at once
        (both filter active)."""
        self._require_admin(admin)
        target = await self._load_target(admin, target_id)
        if not active:
            if target.id == admin.id:
                raise APIException(403, "CANNOT_MODIFY_SELF", "You can't deactivate your own account")
            await self._guard_last_admin(target)
        target.active = active
        await self.db.commit()
        await self.db.refresh(target)
        return target

    async def delete_admin(self, admin: SchoolAdmin, target_id: uuid.UUID) -> None:
        """Hard-delete another admin (admin-only). Can't delete yourself or the last
        active admin."""
        self._require_admin(admin)
        target = await self._load_target(admin, target_id)
        if target.id == admin.id:
            raise APIException(403, "CANNOT_MODIFY_SELF", "You can't delete your own account")
        await self._guard_last_admin(target)
        await self.db.delete(target)
        await self.db.commit()

    async def _load_target(self, admin: SchoolAdmin, target_id: uuid.UUID) -> SchoolAdmin:
        target = (
            await self.db.execute(
                select(SchoolAdmin).where(
                    SchoolAdmin.id == target_id, SchoolAdmin.school_id == admin.school_id
                )
            )
        ).scalar_one_or_none()
        if target is None:
            raise APIException(404, "ADMIN_NOT_FOUND", "Admin not found")
        return target

    async def _guard_last_admin(self, target: SchoolAdmin) -> None:
        """Block an action that would leave the school with zero active admins."""
        if not (target.role == "admin" and target.active):
            return  # only an active admin-role account can be "the last one"
        others = (
            await self.db.execute(
                select(func.count()).select_from(SchoolAdmin).where(
                    SchoolAdmin.school_id == target.school_id,
                    SchoolAdmin.role == "admin",
                    SchoolAdmin.active.is_(True),
                    SchoolAdmin.id != target.id,
                )
            )
        ).scalar_one()
        if others == 0:
            raise APIException(422, "LAST_ADMIN", "The school must keep at least one active admin")

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

    async def _pwchange_rate_limit(self, admin_id) -> None:
        try:
            key = rk.pwchange_rate(admin_id)
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, settings.pwchange_window_seconds)
        except RedisError:
            return  # fail-open on the limiter
        if count > settings.pwchange_max_attempts:
            raise APIException(429, "TOO_MANY_ATTEMPTS", "Too many attempts — please try again later")

    async def _clear_pwchange_rate(self, admin_id) -> None:
        try:
            await self.redis.delete(rk.pwchange_rate(admin_id))
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
