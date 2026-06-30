"""Audio endpoints (Sprint 5): Sound Around (F11).

Sound Around issues a `MONITOR` SIM command via Traccar so the watch silently calls the
requesting parent back (CLAUDE.md §3.12 — no media server). Nested under a child like
geofences / emergency contacts. Two-way Call (F12) lands here in Slice 2.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_traccar_gateway
from app.core.database import get_db
from app.core.errors import success
from app.core.redis import get_redis
from app.models.comms import AudioSession
from app.models.user import User
from app.schemas.audio import AudioSessionResponse
from app.services.audio_service import SoundAroundService
from app.services.traccar_gateway import TraccarGateway

router = APIRouter(tags=["audio"])


def _serialize(session: AudioSession) -> dict:
    return AudioSessionResponse.model_validate(session).model_dump(mode="json")


@router.post("/children/{child_id}/sound-around", status_code=201)
async def start_sound_around(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    traccar: TraccarGateway = Depends(get_traccar_gateway),
) -> dict:
    """Start a Sound Around session: gate (can_call + Basic+ + watch online + daily
    quota), dispatch the watch command, and log the session. The watch dials the
    requesting user's phone."""
    session = await SoundAroundService(db, redis, traccar).start(current_user, child_id)
    return success(_serialize(session))
