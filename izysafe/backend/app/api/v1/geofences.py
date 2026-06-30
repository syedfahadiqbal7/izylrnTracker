"""Geofence CRUD endpoints (Sprint 3 Slice 1).

Routes follow the Blueprint contract: create/list nest under a child
(`/children/{child_id}/geofences`); detail/update/delete address a zone directly
(`/geofences/{geofence_id}`). Breach-event history (`/geofences/{id}/events`) lands
with breach detection in a later slice.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import success
from app.core.redis import get_redis
from app.models.location import Geofence
from app.models.user import User
from app.schemas.geofence import GeofenceCreate, GeofenceResponse, GeofenceUpdate
from app.services.geofence_service import GeofenceService

router = APIRouter(tags=["geofences"])


def _serialize(geofence: Geofence) -> dict:
    return GeofenceResponse.model_validate(geofence).model_dump(mode="json")


@router.post("/children/{child_id}/geofences", status_code=201)
async def create_geofence(
    child_id: uuid.UUID,
    payload: GeofenceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Create a zone for a child (requires manage permission + tier headroom)."""
    geofence = await GeofenceService(db, redis).create_geofence(
        current_user, child_id, payload.model_dump(exclude_unset=True)
    )
    return success(_serialize(geofence))


@router.get("/children/{child_id}/geofences")
async def list_geofences(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """List all zones for a child."""
    rows = await GeofenceService(db, redis).list_geofences(current_user, child_id)
    return success([_serialize(g) for g in rows])


@router.get("/geofences/{geofence_id}")
async def get_geofence(
    geofence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    geofence = await GeofenceService(db, redis).get_geofence(current_user, geofence_id, "view")
    return success(_serialize(geofence))


@router.put("/geofences/{geofence_id}")
async def update_geofence(
    geofence_id: uuid.UUID,
    payload: GeofenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Update a zone (requires manage permission)."""
    geofence = await GeofenceService(db, redis).update_geofence(
        current_user, geofence_id, payload.model_dump(exclude_unset=True)
    )
    return success(_serialize(geofence))


@router.delete("/geofences/{geofence_id}")
async def delete_geofence(
    geofence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Delete a zone (requires manage permission)."""
    await GeofenceService(db, redis).delete_geofence(current_user, geofence_id)
    return success({"success": True})
