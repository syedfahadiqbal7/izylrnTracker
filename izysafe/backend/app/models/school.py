"""School tier (Phase 3): schools, school_admins, student_enrollments,
attendance_records, drivers, bus_routes, bus_route_stops, bus_assignments."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UpdatedAtMixin, UUIDPkMixin


class School(Base, UUIDPkMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "schools"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Kolkata")
    holidays: Mapped[list | dict | None] = mapped_column(JSONB)
    on_time_before: Mapped[time] = mapped_column(Time, nullable=False, server_default=text("'09:00'"))
    late_until: Mapped[time] = mapped_column(Time, nullable=False, server_default=text("'11:00'"))
    arrival_window_from: Mapped[time] = mapped_column(
        Time, nullable=False, server_default=text("'07:00'")
    )
    # Weekdays school is in session (ISO 1=Mon..7=Sun) — the absent sweep skips the rest.
    school_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("ARRAY[1,2,3,4,5]")
    )


class SchoolAdmin(Base, UUIDPkMixin, TimestampMixin):
    """School admins authenticate by email + password (bcrypt), separate from parent OTP."""

    __tablename__ = "school_admins"
    __table_args__ = (CheckConstraint("role IN ('admin','staff')", name="ck_school_admin_role"),)

    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="admin")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StudentEnrollment(Base, UUIDPkMixin):
    """Child<->school opt-in. Parent must grant visibility (default OFF)."""

    __tablename__ = "student_enrollments"
    __table_args__ = (
        UniqueConstraint("school_id", "child_id", name="uq_enrollment_school_child"),
        Index("idx_enrollments_school", "school_id", postgresql_where=text("parent_opt_in")),
    )

    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    class_grade: Mapped[str | None] = mapped_column(String(50))
    parent_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    bus_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AttendanceRecord(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "attendance_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('on_time','late','absent','unknown','early')",
            name="ck_attendance_status",
        ),
        UniqueConstraint("school_id", "child_id", "date", name="uq_attendance_day"),
        Index("idx_attendance_school_date", "school_id", "date"),
    )

    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    arrival_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    departure_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unknown")
    total_hours: Mapped[float | None] = mapped_column(Double)
    marked_manually: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Driver(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "drivers"

    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    # bcrypt of the admin-set access code (Sprint 10); null ⇒ driver can't log in yet.
    password_hash: Mapped[str | None] = mapped_column(String(100))
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BusRoute(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "bus_routes"

    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drivers.id", ondelete="SET NULL")
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    active_from: Mapped[time | None] = mapped_column(Time)
    active_to: Mapped[time | None] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class BusRouteStop(Base, UUIDPkMixin):
    __tablename__ = "bus_route_stops"
    __table_args__ = (UniqueConstraint("route_id", "seq", name="uq_stop_route_seq"),)

    route_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bus_routes.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lng: Mapped[float] = mapped_column(Double, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_at: Mapped[time | None] = mapped_column(Time)


class BusAssignment(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "bus_assignments"
    __table_args__ = (UniqueConstraint("route_id", "child_id", name="uq_bus_route_child"),)

    route_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bus_routes.id", ondelete="CASCADE"), nullable=False
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    stop_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bus_route_stops.id", ondelete="SET NULL")
    )


class BusTrip(Base, UUIDPkMixin):
    """A driver-run trip on a route (Sprint 10). One active trip per route (partial
    unique index); the driver marks arrivals/boardings against it."""

    __tablename__ = "bus_trips"
    __table_args__ = (
        CheckConstraint("status IN ('active','ended')", name="ck_bus_trip_status"),
        Index("idx_bus_trips_driver", "driver_id"),
    )

    route_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bus_routes.id", ondelete="CASCADE"), nullable=False
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drivers.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BusBoarding(Base, UUIDPkMixin):
    """A child's manual pickup confirmation during a trip (one per child per trip)."""

    __tablename__ = "bus_boardings"
    __table_args__ = (UniqueConstraint("trip_id", "child_id", name="uq_boarding_trip_child"),)

    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bus_trips.id", ondelete="CASCADE"), nullable=False
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    stop_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bus_route_stops.id", ondelete="SET NULL")
    )
    boarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
