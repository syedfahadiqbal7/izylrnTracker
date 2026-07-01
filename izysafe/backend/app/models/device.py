"""Devices & pairing: devices, pairing_codes."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UpdatedAtMixin, UUIDPkMixin

_DEVICE_TYPE_CHECK = "device_type IN ('watch','bag_tracker','phone')"


class Device(Base, UUIDPkMixin, TimestampMixin, UpdatedAtMixin, SoftDeleteMixin):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(_DEVICE_TYPE_CHECK, name="ck_device_type"),
        CheckConstraint("protocol IN ('gt06','tk103','h02')", name="ck_device_protocol"),
        CheckConstraint("battery_threshold IN (10,15,20,30)", name="ck_device_batt_threshold"),
        CheckConstraint(
            "watch_removed_threshold_min IN (5,10,15)", name="ck_device_removed_threshold"
        ),
        CheckConstraint("last_battery BETWEEN 0 AND 100", name="ck_device_last_battery"),
        Index("idx_devices_child", "child_id"),
        Index("idx_devices_traccar", "traccar_id"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="watch")
    imei: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    traccar_id: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(30))
    protocol: Mapped[str | None] = mapped_column(String(20), server_default="gt06")
    battery_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20")
    watch_removed_threshold_min: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="10"
    )
    # Watch Removed (F18) opt-in switch; the threshold above is always present.
    watch_removed_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    last_battery: Mapped[int | None] = mapped_column(Integer)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    child: Mapped["Child"] = relationship(back_populates="devices")  # noqa: F821


class PairingCode(Base, TimestampMixin):
    __tablename__ = "pairing_codes"
    __table_args__ = (
        CheckConstraint(_DEVICE_TYPE_CHECK, name="ck_pairing_device_type"),
    )

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    device_type: Mapped[str] = mapped_column(String(20), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # 30-minute default TTL (resolved constant, CLAUDE.md §3.8)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW() + INTERVAL '30 minutes'"),
    )
