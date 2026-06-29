"""SOS & emergency: sos_events, emergency_contacts."""
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
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class SosEvent(Base, UUIDPkMixin):
    """One active SOS per child is enforced by a partial unique index
    (uq_sos_one_active_per_child) defined in the migration."""

    __tablename__ = "sos_events"
    __table_args__ = (
        CheckConstraint("status IN ('active','resolved')", name="ck_sos_status"),
        Index("idx_sos_child_time", "child_id", text("triggered_at DESC")),
        Index(
            "uq_sos_one_active_per_child",
            "child_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    lat: Mapped[float | None] = mapped_column(Double)
    lng: Mapped[float | None] = mapped_column(Double)
    address: Mapped[str | None] = mapped_column(Text)
    approximate: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class EmergencyContact(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "emergency_contacts"
    __table_args__ = (Index("idx_emergency_contacts_child", "child_id"),)

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    relationship_label: Mapped[str | None] = mapped_column("relationship", String(30))
    is_app_user: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
