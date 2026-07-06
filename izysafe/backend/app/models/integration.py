"""Integrations (Phase 3): izylrn_links, wearable_integrations, translations (i18n),
menu_items (admin-managed dynamic navigation)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UpdatedAtMixin, UUIDPkMixin


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
    """i18n strings (F23). PK is the translation key; one column per supported locale.

    Wide format (key + en/hi/ar) — chosen so the admin localization editor edits one
    row per key across all languages, and a per-locale bundle (GET /i18n/{locale}) is a
    single column projection. Admin-managed via the Web Admin Panel (no hard-coded UI
    strings). `updated_at` surfaces the last edit in the editor.
    """

    __tablename__ = "translations"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    en: Mapped[str] = mapped_column(Text, nullable=False)
    hi: Mapped[str | None] = mapped_column(Text)
    ar: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MenuItem(Base, UUIDPkMixin, TimestampMixin, UpdatedAtMixin):
    """Admin-managed navigation item (F23). Drives the Web Admin sidebar (and later the
    mobile nav) dynamically — admins create/reorder/show-hide items and restrict them by
    role, all from the panel. `label_key` points at a `translations` row so labels are
    localized; `icon` is a lucide icon name resolved client-side; `roles` is the set of
    roles that may see the item (empty ⇒ everyone). App-wide config (not school-scoped).
    """

    __tablename__ = "menu_items"
    __table_args__ = (
        CheckConstraint("platform IN ('web','mobile')", name="ck_menu_item_platform"),
    )

    item_key: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    label_key: Mapped[str] = mapped_column(String(120), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(40))
    path: Mapped[str] = mapped_column(String(120), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False, server_default="web")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    roles: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[\"admin\",\"staff\"]'::jsonb")
    )
