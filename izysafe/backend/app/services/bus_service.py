"""Bus roster & routes (Sprint 8 Slice 4, F28).

CRUD for drivers, routes, ordered stops, and child↔route assignments — all owned by
the authenticated admin's school (the owning `school_id` never comes from the payload).
Cross-references are validated to belong to the same school: a route's driver/device,
a stop's route, an assignment's route + stop, and the assigned child must be an opted-in
enrollee (reusing `EnrollmentService.require_enrolled_child`, the privacy backbone).

A route's `device_id` (the bus GPS tracker) must be a `device_type='bus'` device; live
tracking off it is wired in Slice 5.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIException
from app.core.security import hash_secret
from app.models.child import Child
from app.models.device import Device
from app.models.school import (
    BusAssignment,
    BusRoute,
    BusRouteStop,
    Driver,
    SchoolAdmin,
    StudentEnrollment,
)
from app.services.audit_service import AuditService
from app.services.enrollment_service import EnrollmentService


class BusService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.enrollments = EnrollmentService(db)

    # --------------------------------------------------------- bus devices
    async def register_bus(self, admin: SchoolAdmin, data: dict[str, Any]) -> Device:
        """Register a bus GPS tracker as a school-owned, child-less device (F28)."""
        dupe = (
            await self.db.execute(select(Device.id).where(Device.imei == data["imei"]))
        ).first()
        if dupe is not None:
            raise APIException(409, "IMEI_TAKEN", "A device with this IMEI already exists")
        bus = Device(
            school_id=admin.school_id, child_id=None, device_type="bus", **data
        )
        self.db.add(bus)
        await self.db.commit()
        await self.db.refresh(bus)
        return bus

    async def list_buses(self, admin: SchoolAdmin) -> list[Device]:
        return list((
            await self.db.execute(
                select(Device).where(
                    Device.school_id == admin.school_id,
                    Device.device_type == "bus",
                    Device.deleted_at.is_(None),
                ).order_by(Device.created_at)
            )
        ).scalars().all())

    async def delete_bus(self, admin: SchoolAdmin, device_id: uuid.UUID) -> None:
        bus = (
            await self.db.execute(
                select(Device).where(
                    Device.id == device_id, Device.school_id == admin.school_id,
                    Device.device_type == "bus", Device.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if bus is None:
            raise APIException(404, "BUS_NOT_FOUND", "Bus device not found")
        await self.db.delete(bus)  # bus_routes.device_id → SET NULL
        await self.db.commit()

    # ------------------------------------------------------------- drivers
    async def create_driver(self, admin: SchoolAdmin, data: dict[str, Any]) -> Driver:
        data = dict(data)
        code = data.pop("access_code", None)  # optional login code → bcrypt hash
        await self._ensure_phone_free(data.get("phone"))
        driver = Driver(
            school_id=admin.school_id,
            password_hash=hash_secret(code) if code else None,
            **data,
        )
        self.db.add(driver)
        await self.db.flush()
        AuditService.log(self.db, action="driver.create", actor_type="school_admin",
                         actor_id=admin.id, school_id=admin.school_id,
                         entity_type="driver", entity_id=driver.id,
                         details={"name": driver.name, "has_code": driver.password_hash is not None})
        await self.db.commit()
        await self.db.refresh(driver)
        return driver

    async def set_driver_code(self, admin: SchoolAdmin, driver_id: uuid.UUID, code: str) -> Driver:
        """(Re)set a driver's login access code (admin action)."""
        driver = await self._require(admin, Driver, driver_id, "DRIVER_NOT_FOUND")
        driver.password_hash = hash_secret(code)
        AuditService.log(self.db, action="driver.set_code", actor_type="school_admin",
                         actor_id=admin.id, school_id=admin.school_id,
                         entity_type="driver", entity_id=driver.id)
        await self.db.commit()
        await self.db.refresh(driver)
        return driver

    async def _ensure_phone_free(self, phone: str | None) -> None:
        if not phone:
            return
        taken = (
            await self.db.execute(select(Driver.id).where(Driver.phone == phone))
        ).first()
        if taken is not None:
            raise APIException(409, "DRIVER_PHONE_TAKEN", "A driver with this phone already exists")

    async def list_drivers(self, admin: SchoolAdmin) -> list[Driver]:
        return list((
            await self.db.execute(
                select(Driver).where(Driver.school_id == admin.school_id).order_by(Driver.created_at)
            )
        ).scalars().all())

    async def update_driver(self, admin: SchoolAdmin, driver_id: uuid.UUID, fields: dict[str, Any]) -> Driver:
        driver = await self._require(admin, Driver, driver_id, "DRIVER_NOT_FOUND")
        new_phone = fields.get("phone")
        if new_phone is not None and new_phone != driver.phone:
            await self._ensure_phone_free(new_phone)
        for k, v in fields.items():
            setattr(driver, k, v)
        await self.db.commit()
        await self.db.refresh(driver)
        return driver

    async def delete_driver(self, admin: SchoolAdmin, driver_id: uuid.UUID) -> None:
        driver = await self._require(admin, Driver, driver_id, "DRIVER_NOT_FOUND")
        await self.db.delete(driver)  # bus_routes.driver_id → SET NULL
        await self.db.commit()

    # -------------------------------------------------------------- routes
    async def create_route(self, admin: SchoolAdmin, data: dict[str, Any]) -> BusRoute:
        await self._validate_route_refs(admin, data)
        route = BusRoute(school_id=admin.school_id, **data)
        self.db.add(route)
        await self.db.commit()
        await self.db.refresh(route)
        return route

    async def list_routes(self, admin: SchoolAdmin) -> list[BusRoute]:
        return list((
            await self.db.execute(
                select(BusRoute).where(BusRoute.school_id == admin.school_id).order_by(BusRoute.created_at)
            )
        ).scalars().all())

    async def get_route(self, admin: SchoolAdmin, route_id: uuid.UUID) -> BusRoute:
        return await self._require(admin, BusRoute, route_id, "ROUTE_NOT_FOUND")

    async def update_route(self, admin: SchoolAdmin, route_id: uuid.UUID, fields: dict[str, Any]) -> BusRoute:
        route = await self._require(admin, BusRoute, route_id, "ROUTE_NOT_FOUND")
        await self._validate_route_refs(admin, fields)
        for k, v in fields.items():
            setattr(route, k, v)
        await self.db.commit()
        await self.db.refresh(route)
        return route

    async def delete_route(self, admin: SchoolAdmin, route_id: uuid.UUID) -> None:
        route = await self._require(admin, BusRoute, route_id, "ROUTE_NOT_FOUND")
        await self.db.delete(route)  # stops + assignments cascade
        await self.db.commit()

    # --------------------------------------------------------------- stops
    async def add_stop(self, admin: SchoolAdmin, route_id: uuid.UUID, data: dict[str, Any]) -> BusRouteStop:
        await self._require(admin, BusRoute, route_id, "ROUTE_NOT_FOUND")
        await self._ensure_seq_free(route_id, data["seq"])
        stop = BusRouteStop(route_id=route_id, **data)
        self.db.add(stop)
        await self.db.commit()
        await self.db.refresh(stop)
        return stop

    async def list_stops(self, admin: SchoolAdmin, route_id: uuid.UUID) -> list[BusRouteStop]:
        await self._require(admin, BusRoute, route_id, "ROUTE_NOT_FOUND")
        return list((
            await self.db.execute(
                select(BusRouteStop).where(BusRouteStop.route_id == route_id).order_by(BusRouteStop.seq)
            )
        ).scalars().all())

    async def update_stop(self, admin: SchoolAdmin, stop_id: uuid.UUID, fields: dict[str, Any]) -> BusRouteStop:
        stop = await self._require_stop(admin, stop_id)
        if "seq" in fields and fields["seq"] is not None and fields["seq"] != stop.seq:
            await self._ensure_seq_free(stop.route_id, fields["seq"])
        for k, v in fields.items():
            setattr(stop, k, v)
        await self.db.commit()
        await self.db.refresh(stop)
        return stop

    async def reorder_stops(
        self, admin: SchoolAdmin, route_id: uuid.UUID, stop_ids: list[uuid.UUID]
    ) -> list[BusRouteStop]:
        """Atomically renumber a route's stops to the given order (seq 1..N).

        Uses a two-phase reassign (bump to a free high range, then final 1..N) so the
        unique (route_id, seq) constraint is never violated mid-transaction."""
        await self._require(admin, BusRoute, route_id, "ROUTE_NOT_FOUND")
        stops = (
            await self.db.execute(
                select(BusRouteStop).where(BusRouteStop.route_id == route_id)
            )
        ).scalars().all()
        by_id = {s.id: s for s in stops}
        if len(stop_ids) != len(stops) or set(stop_ids) != set(by_id):
            raise APIException(
                400, "INVALID_ORDER", "The order must list every stop on this route exactly once"
            )
        base = max((s.seq for s in stops), default=0) + 1
        for i, s in enumerate(stops):          # phase 1: park in a free unique range
            s.seq = base + i
        await self.db.flush()
        for i, sid in enumerate(stop_ids, start=1):  # phase 2: final 1..N
            by_id[sid].seq = i
        await self.db.commit()
        return sorted(by_id.values(), key=lambda s: s.seq)

    async def delete_stop(self, admin: SchoolAdmin, stop_id: uuid.UUID) -> None:
        stop = await self._require_stop(admin, stop_id)
        await self.db.delete(stop)  # bus_assignments.stop_id → SET NULL
        await self.db.commit()

    # --------------------------------------------------------- assignments
    async def assign(self, admin: SchoolAdmin, route_id: uuid.UUID, data: dict[str, Any]) -> tuple[BusAssignment, Child]:
        route = await self._require(admin, BusRoute, route_id, "ROUTE_NOT_FOUND")
        enrollment = await self._require(admin, StudentEnrollment, data["enrollment_id"], "ENROLLMENT_NOT_FOUND")
        # The child must be an opted-in student of this school (privacy backbone).
        await self.enrollments.require_enrolled_child(admin, enrollment.child_id)

        stop_id = data.get("stop_id")
        if stop_id is not None:
            stop = await self._require_stop(admin, stop_id)
            if stop.route_id != route.id:
                raise APIException(400, "STOP_NOT_ON_ROUTE", "That stop isn't on this route")

        existing = (
            await self.db.execute(
                select(BusAssignment).where(
                    BusAssignment.route_id == route_id, BusAssignment.child_id == enrollment.child_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise APIException(409, "ALREADY_ASSIGNED", "This student is already assigned to the route")

        assignment = BusAssignment(route_id=route_id, child_id=enrollment.child_id, stop_id=stop_id)
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
        child = (await self.db.execute(select(Child).where(Child.id == enrollment.child_id))).scalar_one()
        return assignment, child

    async def list_assignments(self, admin: SchoolAdmin, route_id: uuid.UUID) -> list[tuple[BusAssignment, Child]]:
        await self._require(admin, BusRoute, route_id, "ROUTE_NOT_FOUND")
        rows = (
            await self.db.execute(
                select(BusAssignment, Child)
                .join(Child, Child.id == BusAssignment.child_id)
                .where(BusAssignment.route_id == route_id)
                .order_by(BusAssignment.created_at)
            )
        ).all()
        return [(a, c) for a, c in rows]

    async def unassign(self, admin: SchoolAdmin, assignment_id: uuid.UUID) -> None:
        assignment = (
            await self.db.execute(
                select(BusAssignment)
                .join(BusRoute, BusRoute.id == BusAssignment.route_id)
                .where(BusAssignment.id == assignment_id, BusRoute.school_id == admin.school_id)
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise APIException(404, "ASSIGNMENT_NOT_FOUND", "Assignment not found")
        await self.db.delete(assignment)
        await self.db.commit()

    # ------------------------------------------------------------- helpers
    async def _require(self, admin: SchoolAdmin, model, obj_id: uuid.UUID, code: str):
        """Load a school-owned row by id, or 404 (never reveal another school's row)."""
        obj = (
            await self.db.execute(
                select(model).where(model.id == obj_id, model.school_id == admin.school_id)
            )
        ).scalar_one_or_none()
        if obj is None:
            raise APIException(404, code, "Not found")
        return obj

    async def _require_stop(self, admin: SchoolAdmin, stop_id: uuid.UUID) -> BusRouteStop:
        stop = (
            await self.db.execute(
                select(BusRouteStop)
                .join(BusRoute, BusRoute.id == BusRouteStop.route_id)
                .where(BusRouteStop.id == stop_id, BusRoute.school_id == admin.school_id)
            )
        ).scalar_one_or_none()
        if stop is None:
            raise APIException(404, "STOP_NOT_FOUND", "Stop not found")
        return stop

    async def _ensure_seq_free(self, route_id: uuid.UUID, seq: int) -> None:
        taken = (
            await self.db.execute(
                select(BusRouteStop.id).where(
                    BusRouteStop.route_id == route_id, BusRouteStop.seq == seq
                )
            )
        ).first()
        if taken is not None:
            raise APIException(409, "STOP_SEQ_TAKEN", f"Stop #{seq} already exists on this route")

    async def _validate_route_refs(self, admin: SchoolAdmin, data: dict[str, Any]) -> None:
        driver_id = data.get("driver_id")
        if driver_id is not None:
            await self._require(admin, Driver, driver_id, "DRIVER_NOT_FOUND")
        device_id = data.get("device_id")
        if device_id is not None:
            device = (
                await self.db.execute(
                    select(Device).where(Device.id == device_id, Device.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            if device is None or device.device_type != "bus" or device.school_id != admin.school_id:
                raise APIException(400, "INVALID_BUS_DEVICE", "device_id must be a bus device of this school")
