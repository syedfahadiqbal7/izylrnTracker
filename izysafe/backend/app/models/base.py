"""Declarative base + shared column mixins.

Conventions (CLAUDE.md §6):
  * UUID primary keys (server-side gen_random_uuid) on relational tables.
  * TIMESTAMPTZ stored in UTC (DateTime(timezone=True)).
  * created_at / updated_at server defaults; updated_at also maintained by a DB
    trigger (set_updated_at) defined in the migration — onupdate here is belt-and-braces.
  * Soft delete via nullable deleted_at on users / children / devices.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """All models inherit from this; Base.metadata is Alembic's target."""


class UUIDPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
