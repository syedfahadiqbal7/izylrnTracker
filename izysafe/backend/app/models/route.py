"""Safe routes & public share links."""
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
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UpdatedAtMixin, UUIDPkMixin


class SafeRoute(Base, UUIDPkMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "safe_routes"
    __table_args__ = (
        CheckConstraint(
            "deviation_tolerance_m BETWEEN 100 AND 500", name="ck_route_tolerance"
        ),
        Index("idx_safe_routes_child", "child_id", postgresql_where=text("active")),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    waypoints: Mapped[list | dict] = mapped_column(JSONB, nullable=False)
    deviation_tolerance_m: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="200"
    )
    active_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("ARRAY[1,2,3,4,5]")
    )
    active_from: Mapped[datetime] = mapped_column(Time, nullable=False)
    active_to: Mapped[datetime] = mapped_column(Time, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class ShareLink(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "share_links"
    __table_args__ = (Index("idx_share_links_token", "token"),)

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
