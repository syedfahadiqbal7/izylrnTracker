"""Communication (Phase 2): audio_sessions, call_records, chat_messages."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class AudioSession(Base, UUIDPkMixin, TimestampMixin):
    """Sound Around (F11) privacy audit log — also supports the consent requirement."""

    __tablename__ = "audio_sessions"
    __table_args__ = (Index("idx_audio_sessions_child_time", "child_id", "started_at"),)

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    duration_s: Mapped[int | None] = mapped_column(Integer)


class CallRecord(Base, UUIDPkMixin):
    __tablename__ = "call_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('initiated','answered','missed','failed')", name="ck_call_status"
        ),
        Index("idx_call_records_child_time", "child_id", "started_at"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    initiated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="initiated")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer)


class ChatMessage(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("sender_type IN ('parent','child')", name="ck_chat_sender_type"),
        CheckConstraint(
            "status IN ('queued','sent','delivered','failed')", name="ck_chat_status"
        ),
        Index("idx_chat_child_time", "child_id", "created_at"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    sender_type: Mapped[str] = mapped_column(String(10), nullable=False)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="sent")
