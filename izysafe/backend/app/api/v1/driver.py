"""Driver app endpoints (Sprint 10 Slice 1).

School-issued login (phone + admin-set access code) → `driver`-scoped JWT, then read
views of the driver's own routes. Auth mirrors the school-admin flow (refresh rotation +
denylist). Read-only in this slice — trip start/end + manual marking come later.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    DriverContext,
    get_current_driver,
    get_current_driver_auth,
    get_fcm_gateway,
)
from app.core.database import get_db
from app.core.errors import success
from app.core.redis import get_redis
from app.models.school import Driver
from app.schemas.auth import LogoutRequest, RefreshRequest
from app.schemas.bus import (
    BoardingResponse,
    DriverLoginRequest,
    DriverProfileResponse,
    DriverRouteResponse,
    TripResponse,
    TripStartRequest,
)
from app.schemas.school import TokenPairResponse
from app.services.driver_service import DriverAuthService, DriverService, DriverTripService
from app.services.fcm_gateway import FcmGateway

router = APIRouter(prefix="/drivers", tags=["driver-app"])


@router.post("/auth/login")
async def login(
    payload: DriverLoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Driver login with phone + access code → JWT access+refresh pair (scope `driver`)."""
    tokens = await DriverAuthService(db, redis).login(payload.phone, payload.code)
    return success(TokenPairResponse(**tokens).model_dump())


@router.post("/auth/refresh")
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    tokens = await DriverAuthService(db, redis).refresh(payload.refresh_token)
    return success(TokenPairResponse(**tokens).model_dump())


@router.delete("/auth/logout")
async def logout(
    payload: LogoutRequest,
    auth: DriverContext = Depends(get_current_driver_auth),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    await DriverAuthService(db, redis).logout(auth.payload, payload.refresh_token)
    return success({"success": True})


@router.get("/me")
async def current_driver(driver: Driver = Depends(get_current_driver)) -> dict:
    """The authenticated driver's profile."""
    return success(DriverProfileResponse.model_validate(driver).model_dump(mode="json"))


@router.get("/me/routes")
async def my_routes(
    driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The driver's active routes, each with ordered stops + the assigned roster."""
    rows = await DriverService(db).today_routes(driver)
    return success([DriverRouteResponse(**r).model_dump(mode="json") for r in rows])


# --------------------------------------------------------------- trip actions
def _trip_service(db: AsyncSession, redis: Redis, fcm: FcmGateway) -> DriverTripService:
    return DriverTripService(db, redis, fcm)


@router.post("/me/trip/start", status_code=201)
async def start_trip(
    payload: TripStartRequest,
    driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> dict:
    """Start a trip on one of the driver's active routes."""
    trip = await _trip_service(db, redis, fcm).start_trip(driver, payload.route_id)
    return success(TripResponse.model_validate(trip).model_dump(mode="json"))


@router.post("/me/trip/end")
async def end_trip(
    driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> dict:
    """End the driver's active trip."""
    trip = await _trip_service(db, redis, fcm).end_trip(driver)
    return success(TripResponse.model_validate(trip).model_dump(mode="json"))


@router.post("/me/stop/{stop_id}/arrived")
async def mark_arrived(
    stop_id: uuid.UUID,
    driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> dict:
    """Announce arrival at a stop → notifies boarding families (bus_arrival)."""
    notified = await _trip_service(db, redis, fcm).mark_arrived(driver, stop_id)
    return success({"success": True, "notified": notified})


@router.post("/me/child/{child_id}/picked-up", status_code=201)
async def mark_picked_up(
    child_id: uuid.UUID,
    driver: Driver = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> dict:
    """Confirm a child boarded at their assigned stop → notifies the family (bus_boarded)."""
    boarding = await _trip_service(db, redis, fcm).mark_picked_up(driver, child_id)
    return success(BoardingResponse.model_validate(boarding).model_dump(mode="json"))
