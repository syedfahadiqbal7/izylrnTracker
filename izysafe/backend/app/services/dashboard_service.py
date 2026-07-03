"""School dashboard stats (Sprint 10, Admin Panel polish).

A single, cheap roll-up for the panel's landing page: live bus count (Redis),
today's present count (per the school's timezone), consent breakdown, and active
trips — all school-scoped.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.models.device import Device
from app.models.school import (
    AttendanceRecord,
    BusRoute,
    BusTrip,
    School,
    SchoolAdmin,
    StudentEnrollment,
)
from app.services.attendance_service import _PRESENT, _local


class DashboardService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis

    async def stats(self, admin: SchoolAdmin) -> dict[str, Any]:
        school = (
            await self.db.execute(select(School).where(School.id == admin.school_id))
        ).scalar_one()
        today = _local(datetime.now(UTC), school.timezone).date()

        bus_ids = (
            await self.db.execute(
                select(Device.id).where(
                    Device.school_id == admin.school_id,
                    Device.device_type == "bus",
                    Device.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        buses_online = 0
        for bid in bus_ids:
            if await self.redis.get(rk.device_online(bid)):
                buses_online += 1

        async def _count(stmt) -> int:
            return (await self.db.execute(stmt)).scalar_one()

        enrolled = await _count(
            select(func.count()).select_from(StudentEnrollment).where(
                StudentEnrollment.school_id == admin.school_id
            )
        )
        consented = await _count(
            select(func.count()).select_from(StudentEnrollment).where(
                StudentEnrollment.school_id == admin.school_id,
                StudentEnrollment.parent_opt_in.is_(True),
            )
        )
        location_consented = await _count(
            select(func.count()).select_from(StudentEnrollment).where(
                StudentEnrollment.school_id == admin.school_id,
                StudentEnrollment.parent_opt_in.is_(True),
                StudentEnrollment.location_opt_in.is_(True),
            )
        )
        present = await _count(
            select(func.count()).select_from(AttendanceRecord).where(
                AttendanceRecord.school_id == admin.school_id,
                AttendanceRecord.date == today,
                AttendanceRecord.status.in_(_PRESENT),
            )
        )
        active_trips = await _count(
            select(func.count())
            .select_from(BusTrip)
            .join(BusRoute, BusRoute.id == BusTrip.route_id)
            .where(BusRoute.school_id == admin.school_id, BusTrip.status == "active")
        )

        return {
            "buses_total": len(bus_ids),
            "buses_online": buses_online,
            "students_enrolled": enrolled,
            "consented": consented,
            "pending_consents": enrolled - consented,
            "location_consented": location_consented,
            "students_present": present,
            "active_trips": active_trips,
        }
