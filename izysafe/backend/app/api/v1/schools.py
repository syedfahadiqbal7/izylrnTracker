"""School / B2B endpoints (Sprint 8 Slice 1) — admin auth + school profile.

Admin auth mirrors the parent flow but under `/schools/auth/*` with email+password and
a `school_admin`-scoped JWT (`get_current_school_admin`). The bootstrap `POST /schools/seed`
is env-gated (no auth — the seed secret is the credential; Decision D1). School config
writes + staff invites require role='admin'.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SchoolAdminContext,
    get_current_school_admin,
    get_current_school_admin_auth,
)
from app.core.database import get_db
from app.core.errors import success
from app.core.redis import get_redis
from app.models.child import Child
from app.models.school import School, SchoolAdmin, StudentEnrollment
from app.schemas.auth import LogoutRequest, RefreshRequest
from app.schemas.school import (
    AttendanceRecordResponse,
    DailyRegisterRow,
    EnrollmentResponse,
    EnrollStudentRequest,
    ManualAttendanceRequest,
    SchoolAdminResponse,
    SchoolLoginRequest,
    SchoolResponse,
    SchoolSeedRequest,
    SchoolUpdateRequest,
    StaffInviteRequest,
    TokenPairResponse,
)
from app.services.attendance_service import AttendanceService
from app.services.enrollment_service import EnrollmentService
from app.services.school_service import SchoolAuthService, SchoolService

router = APIRouter(prefix="/schools", tags=["schools"])


def _admin(a: SchoolAdmin) -> dict:
    return SchoolAdminResponse.model_validate(a).model_dump(mode="json")


def _school(s: School) -> dict:
    return SchoolResponse.model_validate(s).model_dump(mode="json")


def _enrollment(e: StudentEnrollment, child: Child) -> dict:
    return EnrollmentResponse(
        id=e.id, school_id=e.school_id, child_id=e.child_id, child_name=child.name,
        class_grade=e.class_grade, parent_opt_in=e.parent_opt_in,
        bus_opt_in=e.bus_opt_in, enrolled_at=e.enrolled_at,
    ).model_dump(mode="json")


# --------------------------------------------------------------------------- #
# Bootstrap + auth
# --------------------------------------------------------------------------- #
@router.post("/seed", status_code=201)
async def seed_school(
    payload: SchoolSeedRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Env-gated: provision a school + its first admin (the seed secret is the credential)."""
    school, admin = await SchoolAuthService(db, redis).seed(payload.model_dump())
    return success({"school": _school(school), "admin": _admin(admin)})


@router.post("/auth/login")
async def login(
    payload: SchoolLoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Email+password login → JWT access+refresh pair (scoped `school_admin`)."""
    tokens = await SchoolAuthService(db, redis).login(payload.email, payload.password)
    return success(TokenPairResponse(**tokens).model_dump())


@router.post("/auth/refresh")
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Rotate a school-admin refresh token → new access+refresh pair."""
    tokens = await SchoolAuthService(db, redis).refresh(payload.refresh_token)
    return success(TokenPairResponse(**tokens).model_dump())


@router.delete("/auth/logout")
async def logout(
    payload: LogoutRequest,
    auth: SchoolAdminContext = Depends(get_current_school_admin_auth),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Revoke the current access token + the supplied refresh token."""
    await SchoolAuthService(db, redis).logout(auth.payload, payload.refresh_token)
    return success({"success": True})


# --------------------------------------------------------------------------- #
# Admin identity + management
# --------------------------------------------------------------------------- #
@router.get("/admins/me")
async def current_admin(
    admin: SchoolAdmin = Depends(get_current_school_admin),
) -> dict:
    """The authenticated admin's own identity."""
    return success(_admin(admin))


@router.get("/admins")
async def list_admins(
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """List the admins/staff of the caller's school."""
    rows = await SchoolAuthService(db, redis).list_admins(admin)
    return success([_admin(a) for a in rows])


@router.post("/admins", status_code=201)
async def invite_staff(
    payload: StaffInviteRequest,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Add a staff/admin to the caller's school (requires role='admin')."""
    new_admin = await SchoolAuthService(db, redis).invite_staff(admin, payload.model_dump())
    return success(_admin(new_admin))


# --------------------------------------------------------------------------- #
# School profile / config
# --------------------------------------------------------------------------- #
@router.get("/me")
async def get_my_school(
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The caller's school profile + attendance-threshold config."""
    school = await SchoolService(db).get_school(admin)
    return success(_school(school))


@router.put("/me")
async def update_my_school(
    payload: SchoolUpdateRequest,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update school profile/config (requires role='admin')."""
    school = await SchoolService(db).update_school(
        admin, payload.model_dump(exclude_unset=True)
    )
    return success(_school(school))


# --------------------------------------------------------------------------- #
# Roster / enrollment (school side)
# --------------------------------------------------------------------------- #
@router.post("/students", status_code=201)
async def enroll_student(
    payload: EnrollStudentRequest,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enroll a student by the parent's phone → creates a pending-consent enrollment."""
    enrollment, child = await EnrollmentService(db).enroll(admin, payload.model_dump())
    return success(_enrollment(enrollment, child))


@router.get("/students")
async def list_roster(
    class_grade: str | None = Query(None),
    opted_in: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The school's roster (filter by class_grade / consent status)."""
    rows, total = await EnrollmentService(db).list_roster(
        admin, class_grade=class_grade, opted_in=opted_in, limit=limit, offset=offset
    )
    return success(
        [_enrollment(e, c) for e, c in rows],
        meta={"total": total, "limit": limit, "offset": offset},
    )


@router.delete("/students/{enrollment_id}")
async def remove_student(
    enrollment_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove a student from the school's roster."""
    await EnrollmentService(db).remove(admin, enrollment_id)
    return success({"success": True})


# --------------------------------------------------------------------------- #
# Attendance (F27)
# --------------------------------------------------------------------------- #
@router.post("/students/{enrollment_id}/attendance-zone", status_code=201)
async def link_attendance_zone(
    enrollment_id: uuid.UUID,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Link this student's school-zone geofence as the school's attendance anchor (D9)."""
    zone = await AttendanceService(db, redis).link_zone(admin, enrollment_id)
    return success({"geofence_id": str(zone.id), "child_id": str(zone.child_id)})


@router.get("/attendance")
async def daily_register(
    date_: date = Query(..., alias="date"),
    class_grade: str | None = Query(None),
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The daily register: every consented student's status for a date."""
    rows = await AttendanceService(db).daily_register(admin, date_, class_grade)
    return success([DailyRegisterRow(**r).model_dump(mode="json") for r in rows])


@router.get("/students/{enrollment_id}/attendance")
async def child_attendance_history(
    enrollment_id: uuid.UUID,
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """A student's attendance history over a date range."""
    rows = await AttendanceService(db).child_history(admin, enrollment_id, date_from, date_to)
    return success([AttendanceRecordResponse.model_validate(r).model_dump(mode="json") for r in rows])


@router.put("/students/{enrollment_id}/attendance")
async def set_manual_attendance(
    enrollment_id: uuid.UUID,
    payload: ManualAttendanceRequest,
    admin: SchoolAdmin = Depends(get_current_school_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually set/override a student's attendance status for a date."""
    rec = await AttendanceService(db).set_manual(admin, enrollment_id, payload.date, payload.status)
    return success(AttendanceRecordResponse.model_validate(rec).model_dump(mode="json"))
