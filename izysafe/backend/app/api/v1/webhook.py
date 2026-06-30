"""Traccar webhooks (Flow A position forwarding).

Authenticated by the shared secret header, never JWT (CLAUDE.md §7). The handler
always returns 200 so Traccar's forward queue never backs up — unknown devices and
invalid fixes are acknowledged and dropped, not retried.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_battery_service,
    get_device_status_service,
    get_geofence_breach_service,
    get_realtime_gateway,
    get_sos_service,
    get_speed_service,
    verify_traccar_secret,
)
from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.location import TraccarForward
from app.services.battery_service import BatteryService
from app.services.device_status import DeviceStatusService
from app.services.geofence_breach_service import GeofenceBreachService
from app.services.location_service import LocationService, _coords_valid
from app.services.realtime_gateway import RealtimeGateway
from app.services.sos_service import SosService
from app.services.speed_service import MIN_ALERT_SPEED_KMH, SpeedService

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/traccar", dependencies=[Depends(verify_traccar_secret)])
async def traccar_position(
    body: TraccarForward,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    realtime: RealtimeGateway = Depends(get_realtime_gateway),
    device_status: DeviceStatusService = Depends(get_device_status_service),
    battery: BatteryService = Depends(get_battery_service),
    speed: SpeedService = Depends(get_speed_service),
    geofence: GeofenceBreachService = Depends(get_geofence_breach_service),
) -> dict:
    """Ingest one decoded position: cache it, mark the device online, buffer it for
    the batch writer (hot path). Off the hot path in BackgroundTasks: the Firebase
    live-map write, the device online-transition reconcile, and the battery + speed
    checks. Returns 200 with the disposition (accepted / ignored)."""
    result = await LocationService(db, redis).process_update(body)
    if not result.stored:
        return {"status": "ignored", "reason": result.reason}

    background.add_task(
        realtime.update_live_location, str(result.child_id), result.live_payload
    )
    background.add_task(device_status.reconcile_online, result.device_id)
    # Geofence breach detection — skipped on stale fixes (an old position must not
    # raise a fresh enter/exit alert; CLAUDE.md §5).
    if not result.stale:
        background.add_task(
            geofence.check_all_fences,
            result.child_id, result.lat, result.lng, result.device_id,
        )
    if result.battery is not None:
        background.add_task(battery.evaluate, result.device_id, result.battery)
    # Only when fast enough to possibly exceed a threshold — skips the DB read for
    # the overwhelmingly common slow/stationary pings.
    if result.speed is not None and result.speed > MIN_ALERT_SPEED_KMH:
        background.add_task(speed.evaluate, result.child_id, result.speed)
    return {"status": "accepted", "stale": result.stale}


@router.post("/traccar/alarm", dependencies=[Depends(verify_traccar_secret)])
async def traccar_alarm(
    body: TraccarForward,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    sos: SosService = Depends(get_sos_service),
) -> dict:
    """Ingest a GT06 SOS alarm (Flow C). Secret-header authed like the position
    webhook; always 200 so Traccar's queue can't back up. Resolution is done inline
    (request session); the dedup/insert/Firebase/urgent-FCM fan-out runs off the hot
    path in a BackgroundTask. Coordinates fall back to the last-known fix when the
    alarm lacks a valid one (the service flags it approximate)."""
    pos = body.position
    alarm = (pos.attributes.alarm or "").lower()
    # This endpoint is SOS-specific: a non-SOS alarm mis-routed here is ignored.
    if alarm and alarm != "sos":
        return {"status": "ignored", "reason": "not_sos_alarm"}

    unique_id = body.device.unique_id if body.device else None
    resolved = await LocationService(db, redis).resolve_device(pos.device_id, unique_id)
    if resolved is None:
        return {"status": "ignored", "reason": "unknown_device"}
    device_id, child_id = resolved

    lat = lng = None
    if pos.valid and _coords_valid(pos.latitude, pos.longitude):
        lat, lng = pos.latitude, pos.longitude

    background.add_task(sos.trigger_from_alarm, child_id, device_id, lat, lng, pos.address)
    return {"status": "accepted"}
