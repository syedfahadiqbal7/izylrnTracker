"""Attendance (Sprint 8 Slice 3, F27) — derived from school-zone geofence transitions.

Split like the other request/background pairs:

  * ``AttendanceEngine`` (session_factory) — the write side. `record_transition` is
    called from the geofence-breach BackgroundTask when a child crosses a geofence that
    carries a `school_id` (Decision D6): a school-day ENTER inside the arrival window
    stamps `arrival_time` + classifies on_time/late; an EXIT stamps `departure_time` +
    `total_hours`. `sweep_absent` is the daily Celery job (Decision D7) that marks
    enrolled+consented children with no record `absent`, skipping non-school weekdays
    (`schools.school_days`) and `schools.holidays`, in each school's own timezone.
    Both are gated on an opted-in enrollment and never overwrite a `marked_manually` row.

  * ``AttendanceService`` (request db) — the read/admin side: daily register, a child's
    history, manual override, and linking a child's school-zone geofence to the school.

All upserts use INSERT … ON CONFLICT so a real-time arrival and the absent sweep can't
collide on the `(school_id, child_id, date)` unique key.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.errors import APIException
from app.models.child import Child
from app.models.location import Geofence
from app.models.school import AttendanceRecord, School, SchoolAdmin, StudentEnrollment
from app.services.audit_service import AuditService

logger = logging.getLogger("izysafe.attendance")

_CONFLICT = ["school_id", "child_id", "date"]
_MAX_REPORT_DAYS = 366          # bound the report/export span
_PRESENT = ("on_time", "late", "early")
_STATUSES = ("on_time", "late", "absent", "early", "unknown")


def _local(now: datetime, tz_name: str) -> datetime:
    try:
        return now.astimezone(ZoneInfo(tz_name))
    except (ZoneInfoNotFoundError, ValueError):
        return now.astimezone(UTC)


def _classify(t: time, school: School) -> str:
    return "on_time" if t <= school.on_time_before else "late"


class AttendanceEngine:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self.session_factory = session_factory

    async def record_transition(
        self, child_id: uuid.UUID, school_id: uuid.UUID, direction: str, now: datetime | None = None
    ) -> None:
        now = now or datetime.now(UTC)
        async with self.session_factory() as session:
            # Consent gate — no opted-in enrollment ⇒ no attendance (Decision B/D5).
            enrolled = (
                await session.execute(
                    select(StudentEnrollment.id).where(
                        StudentEnrollment.school_id == school_id,
                        StudentEnrollment.child_id == child_id,
                        StudentEnrollment.parent_opt_in.is_(True),
                    )
                )
            ).first()
            if enrolled is None:
                return
            school = (
                await session.execute(select(School).where(School.id == school_id))
            ).scalar_one_or_none()
            if school is None:
                return

            local = _local(now, school.timezone)
            today = local.date()

            if direction == "enter":
                if local.time() < school.arrival_window_from:
                    return  # before the window opens → ignore GPS noise
                await session.execute(
                    pg_insert(AttendanceRecord)
                    .values(
                        school_id=school_id, child_id=child_id, date=today,
                        arrival_time=now, status=_classify(local.time(), school),
                    )
                    .on_conflict_do_nothing(index_elements=_CONFLICT)
                )
                rec = await self._get(session, school_id, child_id, today)
                # A pre-existing absent/unknown row (no arrival yet) → stamp the arrival.
                if rec and not rec.marked_manually and rec.arrival_time is None:
                    rec.arrival_time = now
                    rec.status = _classify(local.time(), school)
            else:  # exit
                rec = await self._get(session, school_id, child_id, today)
                if rec and not rec.marked_manually:
                    rec.departure_time = now
                    if rec.arrival_time is not None:
                        rec.total_hours = round(
                            (now - rec.arrival_time).total_seconds() / 3600, 2
                        )
            await session.commit()

    async def sweep_absent(self, now: datetime | None = None) -> int:
        """Mark enrolled+consented no-shows absent for today (per-school tz). Idempotent."""
        now = now or datetime.now(UTC)
        marked = 0
        async with self.session_factory() as session:
            schools = (await session.execute(select(School))).scalars().all()
            for school in schools:
                local = _local(now, school.timezone)
                today = local.date()
                if local.isoweekday() not in (school.school_days or []):
                    continue  # not a school day
                if school.holidays and today.isoformat() in school.holidays:
                    continue  # holiday
                if local.time() < school.late_until:
                    continue  # attendance window still open

                enrolled = set(
                    (await session.execute(
                        select(StudentEnrollment.child_id).where(
                            StudentEnrollment.school_id == school.id,
                            StudentEnrollment.parent_opt_in.is_(True),
                        )
                    )).scalars().all()
                )
                if not enrolled:
                    continue
                have = set(
                    (await session.execute(
                        select(AttendanceRecord.child_id).where(
                            AttendanceRecord.school_id == school.id,
                            AttendanceRecord.date == today,
                        )
                    )).scalars().all()
                )
                for child_id in enrolled - have:
                    await session.execute(
                        pg_insert(AttendanceRecord)
                        .values(school_id=school.id, child_id=child_id, date=today, status="absent")
                        .on_conflict_do_nothing(index_elements=_CONFLICT)
                    )
                    marked += 1
            await session.commit()
        if marked:
            logger.info("Absent sweep marked %d student(s)", marked)
        return marked

    @staticmethod
    async def _get(
        session: AsyncSession, school_id: uuid.UUID, child_id: uuid.UUID, day: date
    ) -> AttendanceRecord | None:
        return (
            await session.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.school_id == school_id,
                    AttendanceRecord.child_id == child_id,
                    AttendanceRecord.date == day,
                )
            )
        ).scalar_one_or_none()


class AttendanceService:
    """Request-path attendance reads + admin actions."""

    def __init__(self, db: AsyncSession, redis: Redis | None = None) -> None:
        self.db = db
        self.redis = redis

    async def link_zone(self, admin: SchoolAdmin, enrollment_id: uuid.UUID) -> Geofence:
        """Designate the child's school-zone geofence as this school's attendance anchor."""
        enrollment = await self._require_enrollment(admin, enrollment_id)
        zones = (
            await self.db.execute(
                select(Geofence).where(
                    Geofence.child_id == enrollment.child_id,
                    Geofence.zone_type == "school",
                )
            )
        ).scalars().all()
        if not zones:
            raise APIException(404, "NO_SCHOOL_ZONE", "The parent hasn't set up a school zone for this child")
        if len(zones) > 1:
            raise APIException(409, "MULTIPLE_SCHOOL_ZONES", "This child has several school zones — can't pick one")

        zone = zones[0]
        zone.school_id = admin.school_id
        await self.db.commit()
        await self.db.refresh(zone)
        if self.redis is not None:  # let the breach engine reload the fence bundle w/ school_id
            try:
                await self.redis.delete(rk.active_fences(enrollment.child_id))
            except Exception:
                logger.warning("Could not invalidate fence cache for child %s", enrollment.child_id)
        return zone

    async def daily_register(
        self, admin: SchoolAdmin, day: date, class_grade: str | None
    ) -> list[dict[str, Any]]:
        """Every consented student's status for a date (no record yet → 'unknown')."""
        conditions = [
            StudentEnrollment.school_id == admin.school_id,
            StudentEnrollment.parent_opt_in.is_(True),
        ]
        if class_grade is not None:
            conditions.append(StudentEnrollment.class_grade == class_grade)

        rows = (
            await self.db.execute(
                select(StudentEnrollment, Child, AttendanceRecord)
                .join(Child, Child.id == StudentEnrollment.child_id)
                .outerjoin(
                    AttendanceRecord,
                    (AttendanceRecord.child_id == StudentEnrollment.child_id)
                    & (AttendanceRecord.school_id == admin.school_id)
                    & (AttendanceRecord.date == day),
                )
                .where(*conditions)
                .order_by(Child.name)
            )
        ).all()
        return [
            {
                "child_id": e.child_id, "child_name": c.name, "class_grade": e.class_grade,
                "status": r.status if r else "unknown",
                "arrival_time": r.arrival_time if r else None,
                "departure_time": r.departure_time if r else None,
            }
            for e, c, r in rows
        ]

    async def report(
        self, admin: SchoolAdmin, date_from: date, date_to: date, class_grade: str | None
    ) -> dict[str, Any]:
        """Date-range summary + per-student rollup over existing attendance_records
        (which the daily sweep fills with 'absent' rows). Opted-in students only."""
        self._guard_range(date_from, date_to)
        conds = self._report_conditions(admin, date_from, date_to, class_grade)

        # Overall counts by status.
        by_status = {s: 0 for s in _STATUSES}
        for status, count in (
            await self.db.execute(
                select(AttendanceRecord.status, func.count())
                .select_from(AttendanceRecord)
                .join(StudentEnrollment, self._enroll_join())
                .join(Child, Child.id == AttendanceRecord.child_id)
                .where(*conds)
                .group_by(AttendanceRecord.status)
            )
        ).all():
            by_status[status] = by_status.get(status, 0) + count
        records = sum(by_status.values())
        present = sum(by_status[s] for s in _PRESENT)

        # Per-student pivot.
        students: dict[uuid.UUID, dict[str, Any]] = {}
        for child_id, name, cg, status, count in (
            await self.db.execute(
                select(AttendanceRecord.child_id, Child.name, StudentEnrollment.class_grade,
                       AttendanceRecord.status, func.count())
                .select_from(AttendanceRecord)
                .join(StudentEnrollment, self._enroll_join())
                .join(Child, Child.id == AttendanceRecord.child_id)
                .where(*conds)
                .group_by(AttendanceRecord.child_id, Child.name, StudentEnrollment.class_grade, AttendanceRecord.status)
            )
        ).all():
            s = students.setdefault(child_id, {
                "child_id": child_id, "child_name": name, "class_grade": cg,
                **{st: 0 for st in _STATUSES},
            })
            s[status] = s.get(status, 0) + count

        per_student = []
        for s in students.values():
            total = sum(s[st] for st in _STATUSES)
            pres = sum(s[st] for st in _PRESENT)
            per_student.append({
                **s, "present_days": pres, "total_days": total,
                "rate": round(pres / total, 3) if total else 0.0,
            })
        per_student.sort(key=lambda x: (x["class_grade"] or "", x["child_name"]))

        return {
            "date_from": date_from, "date_to": date_to, "class_grade": class_grade,
            "summary": {
                "by_status": by_status, "records": records, "students": len(students),
                "present_rate": round(present / records, 3) if records else 0.0,
            },
            "per_student": per_student,
        }

    async def export_rows(
        self, admin: SchoolAdmin, date_from: date, date_to: date, class_grade: str | None
    ) -> list[dict[str, Any]]:
        """Flat per-record rows for the CSV register export."""
        self._guard_range(date_from, date_to)
        conds = self._report_conditions(admin, date_from, date_to, class_grade)
        rows = (
            await self.db.execute(
                select(AttendanceRecord, Child.name, StudentEnrollment.class_grade)
                .select_from(AttendanceRecord)
                .join(StudentEnrollment, self._enroll_join())
                .join(Child, Child.id == AttendanceRecord.child_id)
                .where(*conds)
                .order_by(StudentEnrollment.class_grade, Child.name, AttendanceRecord.date)
            )
        ).all()
        return [
            {
                "date": r.date.isoformat(), "child_id": str(r.child_id), "child_name": name,
                "class_grade": cg or "", "status": r.status,
                "arrival_time": r.arrival_time.isoformat() if r.arrival_time else "",
                "departure_time": r.departure_time.isoformat() if r.departure_time else "",
                "total_hours": r.total_hours if r.total_hours is not None else "",
                "marked_manually": r.marked_manually,
            }
            for r, name, cg in rows
        ]

    @staticmethod
    def _enroll_join():
        return (
            (StudentEnrollment.child_id == AttendanceRecord.child_id)
            & (StudentEnrollment.school_id == AttendanceRecord.school_id)
            & StudentEnrollment.parent_opt_in.is_(True)
        )

    def _report_conditions(self, admin, date_from, date_to, class_grade):
        conds = [
            AttendanceRecord.school_id == admin.school_id,
            AttendanceRecord.date >= date_from,
            AttendanceRecord.date <= date_to,
        ]
        if class_grade is not None:
            conds.append(StudentEnrollment.class_grade == class_grade)
        return conds

    @staticmethod
    def _guard_range(date_from: date, date_to: date) -> None:
        if date_to < date_from:
            raise APIException(422, "INVALID_RANGE", "'to' must be on or after 'from'")
        if (date_to - date_from).days > _MAX_REPORT_DAYS:
            raise APIException(422, "RANGE_TOO_LARGE", f"Range must be at most {_MAX_REPORT_DAYS} days")

    async def child_history(
        self, admin: SchoolAdmin, enrollment_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[AttendanceRecord]:
        enrollment = await self._require_enrollment(admin, enrollment_id, require_opt_in=True)
        rows = (
            await self.db.execute(
                select(AttendanceRecord)
                .where(
                    AttendanceRecord.school_id == admin.school_id,
                    AttendanceRecord.child_id == enrollment.child_id,
                    AttendanceRecord.date >= date_from,
                    AttendanceRecord.date <= date_to,
                )
                .order_by(AttendanceRecord.date.desc())
            )
        ).scalars().all()
        return list(rows)

    async def set_manual(
        self, admin: SchoolAdmin, enrollment_id: uuid.UUID, day: date, status: str
    ) -> AttendanceRecord:
        enrollment = await self._require_enrollment(admin, enrollment_id)
        rec = await AttendanceEngine._get(self.db, admin.school_id, enrollment.child_id, day)
        if rec is None:
            rec = AttendanceRecord(
                school_id=admin.school_id, child_id=enrollment.child_id, date=day,
                status=status, marked_manually=True,
            )
            self.db.add(rec)
        else:
            rec.status = status
            rec.marked_manually = True
        AuditService.log(self.db, action="attendance.manual_override", actor_type="school_admin",
                         actor_id=admin.id, school_id=admin.school_id,
                         entity_type="child", entity_id=enrollment.child_id,
                         details={"date": day.isoformat(), "status": status})
        await self.db.commit()
        await self.db.refresh(rec)
        return rec

    async def _require_enrollment(
        self, admin: SchoolAdmin, enrollment_id: uuid.UUID, *, require_opt_in: bool = False
    ) -> StudentEnrollment:
        enrollment = (
            await self.db.execute(
                select(StudentEnrollment).where(
                    StudentEnrollment.id == enrollment_id,
                    StudentEnrollment.school_id == admin.school_id,
                )
            )
        ).scalar_one_or_none()
        if enrollment is None:
            raise APIException(404, "ENROLLMENT_NOT_FOUND", "Enrollment not found")
        if require_opt_in and not enrollment.parent_opt_in:
            raise APIException(404, "CHILD_NOT_ENROLLED", "Student not found")
        return enrollment
