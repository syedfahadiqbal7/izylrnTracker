"""Notification inbox — every push also lands here."""
from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin

_ALERT_TYPES = (
    "sos","geofence_enter","geofence_exit","low_battery","critical_battery",
    "device_offline","speed","watch_removed","route_deviation","pickup",
    "school_arrival","school_absent","crash","anomaly","chat_reply",
    "family_join","system","bus_arrival",
)


class Alert(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "type IN (" + ",".join(f"'{t}'" for t in _ALERT_TYPES) + ")",
            name="ck_alert_type",
        ),
        Index("idx_alerts_user_unread", "user_id", "read", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    child_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE")
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSONB)
    read: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="false")
