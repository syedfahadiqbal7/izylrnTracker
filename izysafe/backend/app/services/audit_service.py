"""Audit logging (Sprint 10 Slice 2).

`log` adds an `audit_log` row to the CALLER's session (the caller commits) so the action
and its audit entry are atomic. `query` powers the school-admin audit view, scoped to a
school with optional filters + pagination. Never persist secrets — `details` is small
context only.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditService:
    @staticmethod
    def log(
        session: AsyncSession,
        *,
        action: str,
        actor_type: str,
        actor_id: uuid.UUID | None = None,
        school_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Queue an audit entry on `session` (committed by the caller's transaction)."""
        session.add(AuditLog(
            school_id=school_id, actor_type=actor_type, actor_id=actor_id, action=action,
            entity_type=entity_type, entity_id=entity_id, details=details,
        ))

    @staticmethod
    async def query(
        session: AsyncSession,
        school_id: uuid.UUID,
        *,
        actor_type: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        conds = [AuditLog.school_id == school_id]
        if actor_type is not None:
            conds.append(AuditLog.actor_type == actor_type)
        if action is not None:
            conds.append(AuditLog.action == action)
        if entity_type is not None:
            conds.append(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            conds.append(AuditLog.entity_id == entity_id)
        if date_from is not None:
            conds.append(AuditLog.created_at >= date_from)
        if date_to is not None:
            conds.append(AuditLog.created_at <= date_to)

        total = (
            await session.execute(select(func.count()).select_from(AuditLog).where(*conds))
        ).scalar_one()
        rows = (
            await session.execute(
                select(AuditLog).where(*conds)
                .order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), total
