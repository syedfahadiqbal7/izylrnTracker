"""Integrations (Phase 3): izylrn_links, wearable_integrations, translations (i18n)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class IzyLrnLink(Base, UUIDPkMixin):
    """One-way IzyLrn study-status mapping (F29). Live status lives in Redis (4h TTL)."""

    __tablename__ = "izylrn_links"
    __table_args__ = (UniqueConstraint("child_id", name="uq_izylrn_child"),)

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    izylrn_student_id: Mapped[str] = mapped_column(String(100), nullable=False)
    webhook_token: Mapped[str] = mapped_column(String(120), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WearableIntegration(Base, UUIDPkMixin):
    """Garmin/Fitbit OAuth (F32). oauth_refresh_token MUST be encrypted at app layer."""

    __tablename__ = "wearable_integrations"
    __table_args__ = (
        CheckConstraint("provider IN ('garmin','fitbit')", name="ck_wearable_provider"),
        UniqueConstraint("child_id", "provider", name="uq_wearable_child_provider"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    oauth_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Translation(Base):
    """i18n strings (F23). PK is the translation key."""

    __tablename__ = "translations"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    en: Mapped[str] = mapped_column(Text, nullable=False)
    hi: Mapped[str | None] = mapped_column(Text)
    ar: Mapped[str | None] = mapped_column(Text)
