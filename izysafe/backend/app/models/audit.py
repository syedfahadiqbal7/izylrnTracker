"""Audit log (Sprint 10 Slice 2) — a school-scoped trail of sensitive actions.

Cross-domain: the actor may be a school_admin, driver, parent, or system. `school_id`
scopes the school-admin audit query; it's null for actions with no school context.
Never stores secrets — `details` holds small context only.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class AuditLog(Base, UUIDPkMixin):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_school_time", "school_id", "created_at"),
        Index("idx_audit_actor", "actor_id"),
    )

    school_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id", ondelete="SET NULL")
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)   # school_admin|driver|parent|system
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(50), nullable=False)       # dotted, e.g. admin.deactivate
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
