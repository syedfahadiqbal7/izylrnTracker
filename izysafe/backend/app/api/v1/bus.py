"""Bus roster & routes endpoints (Sprint 8 Slice 4, F28).

All under `/schools` with school-admin auth; every row is scoped to the admin's school
in the service. Drivers + routes nest under the school; stops + assignments nest under a
route; stops/assignments are also addressable directly by id for update/delete.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_school_admin
from app.core.database import get_db
from app.core.errors import success
from app.models.child import Child
from app.models.device import Device
from app.models.school import BusAssignment, BusRoute, BusRouteStop, Driver, SchoolAdmin
from app.schemas.bus import (
    AssignmentCreate,
    AssignmentResponse,
    BusDeviceCreate,
    BusDeviceResponse,
    DriverCreate,
    DriverResponse,
    DriverSetCodeRequest,
    DriverUpdate,
    RouteCreate,
    RouteResponse,
    RouteUpdate,
    StopCreate,
    StopResponse,
    StopUpdate,
)
from app.services.bus_service import BusService

router = APIRouter(prefix="/schools", tags=["bus"])


def _driver(d: Driver) -> dict:
    return DriverResponse(
        id=d.id, school_id=d.school_id, name=d.name, phone=d.phone,
        verified=d.verified, active=d.active,
        has_access_code=d.password_hash is not None,
        last_login_at=d.last_login_at, created_at=d.created_at,
    ).model_dump(mode="json")


def _route(r: BusRoute) -> dict:
    return RouteResponse.model_validate(r).model_dump(mode="json")


def _stop(s: BusRouteStop) -> dict:
    return StopResponse.model_validate(s).model_dump(mode="json")


def _assignment(a: BusAssignment, child: Child) -> dict:
    return AssignmentResponse(
        id=a.id, route_id=a.route_id, child_id=a.child_id, child_name=child.name, stop_id=a.stop_id
    ).model_dump(mode="json")


def _bus(d: Device) -> dict:
    return BusDeviceResponse.model_validate(d).model_dump(mode="json")


# ------------------------------------------------------------------- buses
@router.post("/buses", status_code=201)
async def register_bus(
    payload: BusDeviceCreate,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register a bus GPS tracker (a school-owned, child-less device)."""
    return success(_bus(await BusService(db).register_bus(admin, payload.model_dump())))


@router.get("/buses")
async def list_buses(
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return success([_bus(b) for b in await BusService(db).list_buses(admin)])


@router.delete("/buses/{device_id}")
async def delete_bus(
    device_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await BusService(db).delete_bus(admin, device_id)
    return success({"success": True})


# --------------------------------------------------------------------- drivers
@router.post("/drivers", status_code=201)
async def create_driver(
    payload: DriverCreate,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return success(_driver(await BusService(db).create_driver(admin, payload.model_dump())))


@router.get("/drivers")
async def list_drivers(
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return success([_driver(d) for d in await BusService(db).list_drivers(admin)])


@router.put("/drivers/{driver_id}")
async def update_driver(
    driver_id: uuid.UUID,
    payload: DriverUpdate,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    d = await BusService(db).update_driver(admin, driver_id, payload.model_dump(exclude_unset=True))
    return success(_driver(d))


@router.delete("/drivers/{driver_id}")
async def delete_driver(
    driver_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await BusService(db).delete_driver(admin, driver_id)
    return success({"success": True})


@router.post("/drivers/{driver_id}/set-code")
async def set_driver_code(
    driver_id: uuid.UUID,
    payload: DriverSetCodeRequest,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set/rotate a driver's login access code (school-admin action)."""
    driver = await BusService(db).set_driver_code(admin, driver_id, payload.access_code)
    return success(_driver(driver))


# ---------------------------------------------------------------------- routes
@router.post("/routes", status_code=201)
async def create_route(
    payload: RouteCreate,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return success(_route(await BusService(db).create_route(admin, payload.model_dump(exclude_unset=True))))


@router.get("/routes")
async def list_routes(
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return success([_route(r) for r in await BusService(db).list_routes(admin)])


@router.get("/routes/{route_id}")
async def get_route(
    route_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return success(_route(await BusService(db).get_route(admin, route_id)))


@router.put("/routes/{route_id}")
async def update_route(
    route_id: uuid.UUID,
    payload: RouteUpdate,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    r = await BusService(db).update_route(admin, route_id, payload.model_dump(exclude_unset=True))
    return success(_route(r))


@router.delete("/routes/{route_id}")
async def delete_route(
    route_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await BusService(db).delete_route(admin, route_id)
    return success({"success": True})


# ----------------------------------------------------------------------- stops
@router.post("/routes/{route_id}/stops", status_code=201)
async def add_stop(
    route_id: uuid.UUID,
    payload: StopCreate,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return success(_stop(await BusService(db).add_stop(admin, route_id, payload.model_dump())))


@router.get("/routes/{route_id}/stops")
async def list_stops(
    route_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return success([_stop(s) for s in await BusService(db).list_stops(admin, route_id)])


@router.put("/stops/{stop_id}")
async def update_stop(
    stop_id: uuid.UUID,
    payload: StopUpdate,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    s = await BusService(db).update_stop(admin, stop_id, payload.model_dump(exclude_unset=True))
    return success(_stop(s))


@router.delete("/stops/{stop_id}")
async def delete_stop(
    stop_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await BusService(db).delete_stop(admin, stop_id)
    return success({"success": True})


# ----------------------------------------------------------------- assignments
@router.post("/routes/{route_id}/assignments", status_code=201)
async def assign_student(
    route_id: uuid.UUID,
    payload: AssignmentCreate,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    assignment, child = await BusService(db).assign(admin, route_id, payload.model_dump())
    return success(_assignment(assignment, child))


@router.get("/routes/{route_id}/assignments")
async def list_assignments(
    route_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await BusService(db).list_assignments(admin, route_id)
    return success([_assignment(a, c) for a, c in rows])


@router.delete("/assignments/{assignment_id}")
async def unassign_student(
    assignment_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await BusService(db).unassign(admin, assignment_id)
    return success({"success": True})
