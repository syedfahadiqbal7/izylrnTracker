"""Location domain: locations (partitioned), geofences, geofence_events, pickup_events."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UpdatedAtMixin, UUIDPkMixin


class Location(Base):
    """High-volume GPS time-series.

    PARTITIONED BY RANGE (timestamp), one partition per month. The composite PK
    (id, timestamp) is required because the partition key must be part of the PK.
    `child_id` is DENORMALIZED (NOT NULL) so per-child history avoids a devices
    join. No FK on device_id/child_id by design (hot, batch-inserted; see
    schema.sql DESIGN NOTE 6). Monthly partitions + the create_locations_partition
    function are created in the migration, not by the ORM.
    """

    __tablename__ = "locations"
    __table_args__ = (
        Index("idx_locations_device_time", "device_id", text("timestamp DESC")),
        Index("idx_locations_child_time", "child_id", text("timestamp DESC")),
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lng: Mapped[float] = mapped_column(Double, nullable=False)
    accuracy: Mapped[float | None] = mapped_column(Double)
    speed: Mapped[float | None] = mapped_column(Double)
    altitude: Mapped[float | None] = mapped_column(Double)
    bearing: Mapped[float | None] = mapped_column(Double)
    battery: Mapped[int | None] = mapped_column(Integer)
    is_moving: Mapped[bool | None] = mapped_column(Boolean)
    address: Mapped[str | None] = mapped_column(Text)


class Geofence(Base, UUIDPkMixin, TimestampMixin, UpdatedAtMixin):
    """Circle + polygon zones. zone_type also serves Multiple Safe Addresses (F24);
    School Mode keys off zone_type='school'. Schedule is discrete columns (not JSONB)."""

    __tablename__ = "geofences"
    __table_args__ = (
        CheckConstraint(
            "zone_type IN ('home','school','tuition','grandparents','sports','other')",
            name="ck_geofence_zone_type",
        ),
        CheckConstraint("type IN ('circle','polygon')", name="ck_geofence_type"),
        CheckConstraint("radius_m BETWEEN 50 AND 2000", name="ck_geofence_radius"),
        CheckConstraint(
            "(type = 'circle'  AND center_lat IS NOT NULL AND center_lng IS NOT NULL "
            "AND radius_m IS NOT NULL) "
            "OR (type = 'polygon' AND polygon_points IS NOT NULL)",
            name="ck_geofence_shape_valid",
        ),
        Index("idx_geofences_child", "child_id", postgresql_where=text("active")),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="other")
    type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="circle")
    icon: Mapped[str | None] = mapped_column(String(30), server_default="home")
    color: Mapped[str | None] = mapped_column(String(10), server_default="#4CAF50")
    center_lat: Mapped[float | None] = mapped_column(Double)
    center_lng: Mapped[float | None] = mapped_column(Double)
    radius_m: Mapped[int | None] = mapped_column(Integer)
    polygon_points: Mapped[dict | list | None] = mapped_column(JSONB)
    address: Mapped[str | None] = mapped_column(Text)
    notify_enter: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    notify_exit: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    active_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("ARRAY[1,2,3,4,5,6,7]")
    )
    active_from: Mapped[datetime | None] = mapped_column(Time)
    active_to: Mapped[datetime | None] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    child: Mapped["Child"] = relationship(back_populates="geofences")  # noqa: F821


class GeofenceEvent(Base):
    __tablename__ = "geofence_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('enter','exit')", name="ck_geofence_event_type"),
        Index("idx_geofence_events_child_time", "child_id", text("timestamp DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    geofence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geofences.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(10), nullable=False)
    lat: Mapped[float | None] = mapped_column(Double)
    lng: Mapped[float | None] = mapped_column(Double)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PickupEvent(Base, UUIDPkMixin):
    __tablename__ = "pickup_events"
    __table_args__ = (
        CheckConstraint(
            "movement_mode IN ('on_foot','in_vehicle','unknown')", name="ck_pickup_mode"
        ),
        Index("idx_pickup_child_time", "child_id", text("occurred_at DESC")),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    geofence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geofences.id", ondelete="SET NULL")
    )
    movement_mode: Mapped[str | None] = mapped_column(String(10))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
