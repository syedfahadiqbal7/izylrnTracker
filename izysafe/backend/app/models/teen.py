"""Teen driving (Phase 3): trips, crash_events."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Trip(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("safety_score BETWEEN 0 AND 100", name="ck_trip_score"),
        Index("idx_trips_child_time", "child_id", "started_at"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    distance_km: Mapped[float | None] = mapped_column(Double)
    max_speed_kmh: Mapped[float | None] = mapped_column(Double)
    avg_speed_kmh: Mapped[float | None] = mapped_column(Double)
    safety_score: Mapped[int | None] = mapped_column(Integer)
    night_driving: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    phone_use_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sharp_turns: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    route: Mapped[list | dict | None] = mapped_column(JSONB)


class CrashEvent(Base, UUIDPkMixin):
    __tablename__ = "crash_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('detected','false_positive','escalated','resolved')",
            name="ck_crash_status",
        ),
        Index("idx_crash_child_time", "child_id", "detected_at"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="SET NULL")
    )
    lat: Mapped[float | None] = mapped_column(Double)
    lng: Mapped[float | None] = mapped_column(Double)
    g_force: Mapped[float | None] = mapped_column(Double)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="detected")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
