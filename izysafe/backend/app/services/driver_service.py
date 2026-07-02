"""Driver app backend (Sprint 10 Slice 1) — school-issued login + read views.

Drivers are a third identity type (parent OTP · school-admin email+password · driver
phone+code), all sharing the HS256/denylist infra. The admin sets an access code on the
driver (bcrypt-hashed); the driver logs in with phone + code and gets a `driver`-scoped
JWT. Read-only for now: profile + today's assigned routes (stops + roster) over the
Sprint-8 bus tables. Trip start/end + manual marking are a later slice.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.errors import APIException
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_secret
from app.models.child import Child
from app.models.school import (
    BusAssignment, BusBoarding, BusRoute, BusRouteStop, BusTrip, Driver, StudentEnrollment,
)
from app.services.alert_service import AlertService
from app.services.fcm_gateway import FcmGateway
from app.services.token_service import denylist, is_denylisted

logger = logging.getLogger("izysafe.driver")

DRIVER_SCOPE = "driver"
_REDIS_DOWN = APIException(503, "AUTH_BACKEND_UNAVAILABLE", "Please try again in a moment")


class DriverAuthService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis

    async def login(self, phone: str, code: str) -> dict:
        phone = (phone or "").strip()
        await self._check_rate(phone)
        driver = (
            await self.db.execute(
                select(Driver).where(Driver.phone == phone, Driver.active.is_(True))
            )
        ).scalar_one_or_none()
        if driver is None or not driver.password_hash or not verify_secret(code, driver.password_hash):
            await self._bump_fail(phone)
            raise APIException(401, "INVALID_CREDENTIALS", "Incorrect phone or access code")
        await self._clear_fail(phone)
        return self._issue_tokens(driver)

    async def refresh(self, refresh_token: str) -> dict:
        try:
            claims = decode_token(refresh_token, expected_type="refresh")
        except jwt.ExpiredSignatureError:
            raise APIException(401, "TOKEN_EXPIRED", "Session expired — please log in again")
        except (jwt.PyJWTError, ValueError):
            raise APIException(401, "TOKEN_INVALID", "Invalid refresh token")
        if claims.get("scope") != DRIVER_SCOPE:
            raise APIException(401, "TOKEN_INVALID", "Invalid refresh token")

        jti = claims.get("jti")
        if jti:
            try:
                if await is_denylisted(self.redis, "refresh", jti):
                    raise APIException(401, "TOKEN_REVOKED", "Session ended — please log in again")
            except RedisError:
                raise _REDIS_DOWN
        try:
            driver_id = uuid.UUID(str(claims.get("sub")))
        except (ValueError, TypeError):
            raise APIException(401, "TOKEN_INVALID", "Invalid refresh token")
        driver = (
            await self.db.execute(
                select(Driver).where(Driver.id == driver_id, Driver.active.is_(True))
            )
        ).scalar_one_or_none()
        if driver is None:
            raise APIException(401, "DRIVER_NOT_FOUND", "Account not found — please log in again")
        try:
            if jti:
                await denylist(self.redis, "refresh", jti, claims["exp"])
        except RedisError:
            raise _REDIS_DOWN
        return self._issue_tokens(driver)

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

    def _issue_tokens(self, driver: Driver) -> dict:
        extra = {"scope": DRIVER_SCOPE}
        return {
            "access_token": create_access_token(str(driver.id), extra=extra),
            "refresh_token": create_refresh_token(str(driver.id), extra=extra),
            "token_type": "bearer",
        }

    async def _check_rate(self, phone: str) -> None:
        try:
            count = await self.redis.get(rk.driver_login_rate(phone))
        except RedisError:
            return
        if count is not None and int(count) >= settings.driver_login_max_attempts:
            raise APIException(429, "TOO_MANY_ATTEMPTS", "Too many attempts — please try again later")

    async def _bump_fail(self, phone: str) -> None:
        try:
            key = rk.driver_login_rate(phone)
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, settings.driver_login_window_seconds)
        except RedisError:
            pass

    async def _clear_fail(self, phone: str) -> None:
        try:
            await self.redis.delete(rk.driver_login_rate(phone))
        except RedisError:
            pass


class DriverService:
    """Driver-side read views over the bus/route/stop/assignment tables."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def today_routes(self, driver: Driver) -> list[dict[str, Any]]:
        """The driver's active routes, each with ordered stops + the assigned roster."""
        routes = (
            await self.db.execute(
                select(BusRoute).where(
                    BusRoute.driver_id == driver.id, BusRoute.active.is_(True)
                ).order_by(BusRoute.created_at)
            )
        ).scalars().all()

        out: list[dict[str, Any]] = []
        for route in routes:
            stops = (
                await self.db.execute(
                    select(BusRouteStop).where(BusRouteStop.route_id == route.id).order_by(BusRouteStop.seq)
                )
            ).scalars().all()
            roster = (
                await self.db.execute(
                    select(BusAssignment, Child)
                    .join(Child, Child.id == BusAssignment.child_id)
                    .where(BusAssignment.route_id == route.id)
                    .order_by(Child.name)
                )
            ).all()
            active_trip = (
                await self.db.execute(
                    select(BusTrip).where(
                        BusTrip.route_id == route.id, BusTrip.status == "active"
                    )
                )
            ).scalar_one_or_none()
            out.append({
                "route_id": route.id, "name": route.name,
                "active_from": route.active_from, "active_to": route.active_to,
                "active": route.active, "device_id": route.device_id,
                "active_trip": (
                    {"trip_id": active_trip.id, "started_at": active_trip.started_at}
                    if active_trip else None
                ),
                "stops": [
                    {"id": s.id, "name": s.name, "lat": s.lat, "lng": s.lng,
                     "seq": s.seq, "scheduled_at": s.scheduled_at}
                    for s in stops
                ],
                "roster": [
                    {"child_id": a.child_id, "child_name": c.name, "stop_id": a.stop_id}
                    for a, c in roster
                ],
            })
        return out


class DriverTripService:
    """Driver trip lifecycle + manual arrival/boarding (Sprint 10 Slice 1b)."""

    def __init__(self, db: AsyncSession, redis: Redis, fcm: FcmGateway) -> None:
        self.db = db
        self.redis = redis
        self.fcm = fcm

    async def start_trip(self, driver: Driver, route_id: uuid.UUID) -> BusTrip:
        route = await self._require_own_route(driver, route_id)
        if await self._active_trip(driver) is not None:
            raise APIException(409, "TRIP_IN_PROGRESS", "You already have an active trip — end it first")
        existing = (
            await self.db.execute(
                select(BusTrip).where(BusTrip.route_id == route.id, BusTrip.status == "active")
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise APIException(409, "ROUTE_TRIP_ACTIVE", "This route already has an active trip")
        trip = BusTrip(route_id=route.id, driver_id=driver.id, status="active")
        self.db.add(trip)
        await self.db.commit()
        await self.db.refresh(trip)
        logger.info("Driver %s started trip %s on route %s", driver.id, trip.id, route.id)
        return trip

    async def end_trip(self, driver: Driver) -> BusTrip:
        trip = await self._active_trip(driver)
        if trip is None:
            raise APIException(404, "NO_ACTIVE_TRIP", "You have no active trip")
        trip.status = "ended"
        trip.ended_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(trip)
        return trip

    async def mark_arrived(self, driver: Driver, stop_id: uuid.UUID) -> int:
        """Announce arrival at a stop on the active trip → bus_arrival to boarding
        families. Returns the number of families notified."""
        trip = await self._active_trip(driver)
        if trip is None:
            raise APIException(404, "NO_ACTIVE_TRIP", "You have no active trip")
        stop = (
            await self.db.execute(select(BusRouteStop).where(BusRouteStop.id == stop_id))
        ).scalar_one_or_none()
        if stop is None or stop.route_id != trip.route_id:
            raise APIException(400, "STOP_NOT_ON_ROUTE", "That stop isn't on your active route")
        if await self.redis.get(rk.bus_stop_debounce(trip.route_id, stop.id)):
            return 0  # already announced recently

        route = (await self.db.execute(select(BusRoute).where(BusRoute.id == trip.route_id))).scalar_one()
        rows = (
            await self.db.execute(
                select(Child)
                .join(BusAssignment, BusAssignment.child_id == Child.id)
                .join(
                    StudentEnrollment,
                    (StudentEnrollment.child_id == Child.id)
                    & (StudentEnrollment.school_id == route.school_id)
                    & (StudentEnrollment.bus_opt_in.is_(True)),
                )
                .where(BusAssignment.route_id == route.id, BusAssignment.stop_id == stop.id)
            )
        ).scalars().all()
        alerts = AlertService(self.db, self.fcm)
        for child in rows:
            await alerts.notify_family(
                child.id, "bus_arrival", f"Bus arriving at {stop.name}",
                f"{child.name}'s bus is arriving at {stop.name}.",
                {"route_id": str(route.id), "stop_id": str(stop.id), "stop_name": stop.name},
            )
        await self.db.commit()
        await self.redis.set(
            rk.bus_stop_debounce(trip.route_id, stop.id), "1", ex=settings.bus_stop_debounce_seconds
        )
        return len(rows)

    async def mark_picked_up(self, driver: Driver, child_id: uuid.UUID) -> BusBoarding:
        trip = await self._active_trip(driver)
        if trip is None:
            raise APIException(404, "NO_ACTIVE_TRIP", "You have no active trip")
        assignment = (
            await self.db.execute(
                select(BusAssignment).where(
                    BusAssignment.route_id == trip.route_id, BusAssignment.child_id == child_id
                )
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise APIException(404, "CHILD_NOT_ON_ROUTE", "That child isn't assigned to your route")
        dupe = (
            await self.db.execute(
                select(BusBoarding).where(
                    BusBoarding.trip_id == trip.id, BusBoarding.child_id == child_id
                )
            )
        ).scalar_one_or_none()
        if dupe is not None:
            raise APIException(409, "ALREADY_BOARDED", "This child is already marked boarded on this trip")

        boarding = BusBoarding(trip_id=trip.id, child_id=child_id, stop_id=assignment.stop_id)
        self.db.add(boarding)
        child = (await self.db.execute(select(Child).where(Child.id == child_id))).scalar_one()
        await AlertService(self.db, self.fcm).notify_family(
            child_id, "bus_boarded", "Boarded the bus",
            f"{child.name} has boarded the bus.",
            {"trip_id": str(trip.id), "child_id": str(child_id)},
        )
        await self.db.commit()
        await self.db.refresh(boarding)
        logger.info("Driver %s marked child %s boarded on trip %s", driver.id, child_id, trip.id)
        return boarding

    # ---------------------------------------------------------------- helpers
    async def _active_trip(self, driver: Driver) -> BusTrip | None:
        return (
            await self.db.execute(
                select(BusTrip).where(
                    BusTrip.driver_id == driver.id, BusTrip.status == "active"
                )
            )
        ).scalar_one_or_none()

    async def _require_own_route(self, driver: Driver, route_id: uuid.UUID) -> BusRoute:
        route = (
            await self.db.execute(
                select(BusRoute).where(
                    BusRoute.id == route_id, BusRoute.driver_id == driver.id, BusRoute.active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if route is None:
            raise APIException(404, "ROUTE_NOT_FOUND", "Active route not found for you")
        return route
