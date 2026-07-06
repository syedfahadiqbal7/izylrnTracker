"""Device pairing & management endpoints for parents (Sprint 11).

Create/list nest under a child (`/children/{child_id}/devices`); detail/update/delete
address a device directly (`/devices/{device_id}`) — the same shape as geofences. Pairing
registers the tracker in Traccar so its GPS fixes start resolving to the child (Flow A).
Bus devices are managed under `/schools/*`, never here.
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
from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceCreate, DeviceResponse, DeviceUpdate
from app.services.device_service import DeviceService
from app.services.traccar_gateway import TraccarGateway

router = APIRouter(tags=["devices"])


def _serialize(device: Device, online: bool) -> dict:
    resp = DeviceResponse.model_validate(device)
    resp.is_online = online  # live Redis-derived state overrides the cached column
    return resp.model_dump(mode="json")


@router.post("/children/{child_id}/devices", status_code=201)
async def add_device(
    child_id: uuid.UUID,
    payload: DeviceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    traccar: TraccarGateway = Depends(get_traccar_gateway),
) -> dict:
    """Pair a GPS tracker to a child (requires manage permission + device-tier headroom).
    Registers the device in Traccar so its fixes resolve to this child; a null traccar_id
    means Traccar isn't configured yet (pairing still succeeds — graceful seam)."""
    device, online = await DeviceService(db, redis, traccar).add_device(
        current_user, child_id, payload.model_dump(exclude_unset=True)
    )
    return success(_serialize(device, online))


@router.get("/children/{child_id}/devices")
async def list_devices(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    traccar: TraccarGateway = Depends(get_traccar_gateway),
) -> dict:
    """List a child's paired devices with live online status + last-known battery."""
    rows = await DeviceService(db, redis, traccar).list_devices(current_user, child_id)
    return success([_serialize(d, online) for d, online in rows])


@router.get("/devices/{device_id}")
async def get_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    traccar: TraccarGateway = Depends(get_traccar_gateway),
) -> dict:
    device, online = await DeviceService(db, redis, traccar).get_device(current_user, device_id)
    return success(_serialize(device, online))


@router.put("/devices/{device_id}")
async def update_device(
    device_id: uuid.UUID,
    payload: DeviceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    traccar: TraccarGateway = Depends(get_traccar_gateway),
) -> dict:
    """Update device name/color/thresholds/settings (requires manage permission)."""
    device, online = await DeviceService(db, redis, traccar).update_device(
        current_user, device_id, payload.model_dump(exclude_unset=True)
    )
    return success(_serialize(device, online))


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    traccar: TraccarGateway = Depends(get_traccar_gateway),
) -> dict:
    """Unpair a device (soft-delete + remove from Traccar). Requires manage permission."""
    await DeviceService(db, redis, traccar).delete_device(current_user, device_id)
    return success({"success": True})
