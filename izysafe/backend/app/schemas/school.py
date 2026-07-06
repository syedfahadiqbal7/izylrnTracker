"""Pydantic schemas for the School / B2B backend (Sprint 8 Slice 1).

School admins authenticate by email + password (bcrypt), separate from parent OTP
(CLAUDE.md §7). Email is validated with a lightweight regex (no email-validator dep);
passwords are min-8. Time fields (school hours) are plain `time` (HH:MM[:SS]).
"""
from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

AdminRole = Literal["admin", "staff"]


# --------------------------------------------------------------------------- #
# Bootstrap (env-gated seed)
# --------------------------------------------------------------------------- #
class SchoolSeedRequest(BaseModel):
    secret: str                                   # must match settings.school_seed_secret
    school_name: str = Field(..., min_length=1, max_length=200)
    timezone: str = Field("Asia/Kolkata", max_length=64)
    admin_email: str = Field(..., pattern=_EMAIL_RE, max_length=255)
    admin_password: str = Field(..., min_length=8, max_length=100)
    admin_name: str | None = Field(None, max_length=100)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class SchoolLoginRequest(BaseModel):
    email: str = Field(..., pattern=_EMAIL_RE, max_length=255)
    password: str = Field(..., min_length=1, max_length=100)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., pattern=_EMAIL_RE, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=100)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# --------------------------------------------------------------------------- #
# Admin management
# --------------------------------------------------------------------------- #
class StaffInviteRequest(BaseModel):
    email: str = Field(..., pattern=_EMAIL_RE, max_length=255)
    password: str = Field(..., min_length=8, max_length=100)
    name: str | None = Field(None, max_length=100)
    role: AdminRole = "staff"


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=100)
    new_password: str = Field(..., min_length=8, max_length=100)


class SchoolAdminUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)


class SchoolAdminManageRequest(BaseModel):
    """Admin-managing-admin update (role and/or name)."""

    role: AdminRole | None = None
    name: str | None = Field(None, min_length=1, max_length=100)


class SchoolAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    email: str
    name: str | None = None
    role: str
    active: bool
    last_login_at: datetime | None = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# School profile / config
# --------------------------------------------------------------------------- #
class SchoolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    timezone: str
    holidays: list | None = None
    on_time_before: time
    late_until: time
    arrival_window_from: time
    day_ends_at: time
    created_at: datetime
    updated_at: datetime


class SchoolUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    address: str | None = Field(None, max_length=300)
    contact_phone: str | None = Field(None, max_length=20)
    contact_email: str | None = Field(None, max_length=255)
    timezone: str | None = Field(None, max_length=64)
    holidays: list[str] | None = None            # ["2026-08-15", ...] ISO dates
    on_time_before: time | None = None
    late_until: time | None = None
    arrival_window_from: time | None = None
    day_ends_at: time | None = None

    @field_validator("holidays")
    @classmethod
    def _iso_dates(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        from datetime import date
        for d in v:
            date.fromisoformat(d)  # raises ValueError → 422 if malformed
        return v


# --------------------------------------------------------------------------- #
# Enrollment (Slice 2) — school-initiated, parent-consented
# --------------------------------------------------------------------------- #
class EnrollStudentRequest(BaseModel):
    phone: str = Field(..., max_length=20)       # the parent's registered phone
    child_name: str | None = Field(None, max_length=100)  # required if the parent has >1 child
    class_grade: str | None = Field(None, max_length=50)


class EnrollmentResponse(BaseModel):
    """School-facing roster row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    child_id: uuid.UUID
    child_name: str
    class_grade: str | None = None
    parent_name: str | None = None       # primary parent (the enrolling contact)
    parent_phone: str | None = None
    parent_opt_in: bool
    bus_opt_in: bool
    location_opt_in: bool = False
    enrolled_at: datetime


class EnrollmentUpdateRequest(BaseModel):
    """School edits the fields it owns (currently the class/grade)."""

    class_grade: str | None = Field(None, max_length=50)


class ParentEnrollmentResponse(BaseModel):
    """Parent-facing view of a school's enrollment request/consent."""

    id: uuid.UUID
    school_id: uuid.UUID
    school_name: str
    child_id: uuid.UUID
    child_name: str
    class_grade: str | None = None
    parent_opt_in: bool
    bus_opt_in: bool
    location_opt_in: bool = False
    enrolled_at: datetime


class EnrollmentConsentRequest(BaseModel):
    parent_opt_in: bool | None = None            # approve (True) / withdraw (False)
    bus_opt_in: bool | None = None               # separate bus-tracking consent
    location_opt_in: bool | None = None          # separate live-location consent (S10)


# --------------------------------------------------------------------------- #
# Attendance (Slice 3)
# --------------------------------------------------------------------------- #
from datetime import date as _date  # noqa: E402

AttendanceStatus = Literal["on_time", "late", "absent", "unknown", "early"]


class AttendanceRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    date: _date
    arrival_time: datetime | None = None
    departure_time: datetime | None = None
    status: str
    total_hours: float | None = None
    marked_manually: bool


class DailyRegisterRow(BaseModel):
    enrollment_id: uuid.UUID
    child_id: uuid.UUID
    child_name: str
    class_grade: str | None = None
    status: str
    arrival_time: datetime | None = None
    departure_time: datetime | None = None


class ManualAttendanceRequest(BaseModel):
    date: _date
    status: AttendanceStatus
    # Optional local (school-timezone) arrival time-of-day to stamp alongside the
    # status; the service localizes date+time to the school tz then stores UTC.
    arrival_time: time | None = None


class AttendanceReportSummary(BaseModel):
    by_status: dict[str, int]        # {on_time, late, absent, early, unknown}
    records: int
    students: int
    present_rate: float              # (on_time+late+early) / records


class StudentAttendanceSummary(BaseModel):
    child_id: uuid.UUID
    child_name: str
    class_grade: str | None = None
    on_time: int
    late: int
    early: int
    absent: int
    unknown: int
    present_days: int
    total_days: int
    rate: float


class AttendanceReportResponse(BaseModel):
    date_from: _date
    date_to: _date
    class_grade: str | None = None
    summary: AttendanceReportSummary
    per_student: list[StudentAttendanceSummary]


# --------------------------------------------------------------------------- #
# Live child tracking (Sprint 10 — kid trackers)
# --------------------------------------------------------------------------- #
class ChildLivePosition(BaseModel):
    lat: float
    lng: float
    timestamp: str | None = None


class ChildLiveResponse(BaseModel):
    child_id: uuid.UUID
    child_name: str
    class_grade: str | None = None
    device_name: str | None = None
    online: bool
    last_seen: datetime | None = None
    battery: int | None = None
    in_window: bool                       # within school hours/days (live location shown)
    position: ChildLivePosition | None = None


class DashboardStatsResponse(BaseModel):
    buses_total: int
    buses_online: int
    students_enrolled: int
    consented: int
    pending_consents: int
    location_consented: int
    students_present: int
    active_trips: int


# --------------------------------------------------------------------------- #
# Audit log (Slice 2)
# --------------------------------------------------------------------------- #
class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID | None = None
    actor_type: str
    actor_id: uuid.UUID | None = None
    action: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    details: dict | None = None
    created_at: datetime
