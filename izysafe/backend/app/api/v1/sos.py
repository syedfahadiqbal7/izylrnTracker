"""SOS read/resolve endpoints (Sprint 4 Slice 2).

The SOS *trigger* is the Traccar alarm webhook (`/webhook/traccar/alarm`, Slice 1).
These JWT endpoints let the parent app list active emergencies and resolve them.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_realtime_gateway
from app.core.database import get_db
from app.core.errors import success
from app.core.redis import get_redis
from app.models.sos import SosEvent
from app.models.user import User
from app.schemas.sos import SosResponse
from app.services.realtime_gateway import RealtimeGateway
from app.services.sos_service import SosService

router = APIRouter(prefix="/sos", tags=["sos"])


def _serialize(sos: SosEvent, child_name: str) -> dict:
    resp = SosResponse.model_validate(sos)
    resp.child_name = child_name
    return resp.model_dump(mode="json")


@router.get("/active")
async def list_active_sos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    realtime: RealtimeGateway = Depends(get_realtime_gateway),
) -> dict:
    """All active SOS events across the user's children (newest first)."""
    rows = await SosService(db, redis, realtime).list_active(current_user)
    return success([_serialize(sos, name) for sos, name in rows])


@router.put("/{sos_id}/resolve")
async def resolve_sos(
    sos_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    realtime: RealtimeGateway = Depends(get_realtime_gateway),
) -> dict:
    """Resolve an SOS (any family member). Clears the Firebase active flag + Redis
    marker so every parent's full-screen modal dismisses together."""
    sos, child_name = await SosService(db, redis, realtime).resolve(current_user, sos_id)
    return success(_serialize(sos, child_name))
