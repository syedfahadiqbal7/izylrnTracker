"""Traccar webhooks (Flow A position forwarding).

Authenticated by the shared secret header, never JWT (CLAUDE.md §7). The handler
always returns 200 so Traccar's forward queue never backs up — unknown devices and
invalid fixes are acknowledged and dropped, not retried.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_realtime_gateway, verify_traccar_secret
from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.location import TraccarForward
from app.services.location_service import LocationService
from app.services.realtime_gateway import RealtimeGateway

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/traccar", dependencies=[Depends(verify_traccar_secret)])
async def traccar_position(
    body: TraccarForward,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    realtime: RealtimeGateway = Depends(get_realtime_gateway),
) -> dict:
    """Ingest one decoded position: cache it, mark the device online, buffer it for
    the batch writer (hot path). The Firebase live-map write runs off the hot path
    in a BackgroundTask. Returns 200 with the disposition (accepted / ignored)."""
    result = await LocationService(db, redis).process_update(body)
    if not result.stored:
        return {"status": "ignored", "reason": result.reason}

    background.add_task(
        realtime.update_live_location, str(result.child_id), result.live_payload
    )
    return {"status": "accepted", "stale": result.stale}
