"""Alerts inbox endpoints (Sprint 4 Slice 4).

Surfaces the per-user notification inbox that AlertService writes for every alert
(SOS, geofence, battery, speed, device-offline, …). Read-only + mark-read; rows are
created by the alert fan-out, never directly here.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import success
from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertResponse
from app.services.alert_service import AlertInboxService

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _serialize(alert: Alert) -> dict:
    return AlertResponse.model_validate(alert).model_dump(mode="json")


@router.get("")
async def list_alerts(
    unread: bool = Query(False),
    child_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The user's inbox (newest first). `?unread=true` and `?child_id=` filter; meta
    carries page/total + the unread badge count."""
    rows, total, unread_count = await AlertInboxService(db).list(
        current_user, unread=unread, child_id=child_id, page=page, page_size=page_size
    )
    return success(
        [_serialize(a) for a in rows],
        meta={"page": page, "page_size": page_size, "total": total, "unread_count": unread_count},
    )


@router.put("/read-all")
async def mark_all_read(
    child_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark every unread alert read (optionally scoped to one child)."""
    updated = await AlertInboxService(db).mark_all_read(current_user, child_id)
    return success({"updated": updated})


@router.put("/{alert_id}/read")
async def mark_alert_read(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    alert = await AlertInboxService(db).mark_read(current_user, alert_id)
    return success(_serialize(alert))
