"""Live-location ingestion — the hot path of Flow A (CLAUDE.md §5).

`process_update()` runs INLINE in the Traccar webhook and must stay fast and
reliable: resolve device→child, validate, then write only to Redis (latest cache,
online TTL, batch buffer). Everything slower — Firebase, geofence, battery/speed/
status alerts — is scheduled off the hot path in later slices.

Decisions (Sprint 2): unknown device / invalid coords → ack & drop (don't make
Traccar retry); stale-but-valid → still cached + buffered, alerts suppressed
downstream. Device resolution is cached in Redis (traccar_id → device/child, 1h).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.models.device import Device
from app.schemas.location import TraccarForward, TraccarPositionIn

STALE_AFTER_SECONDS = 300  # ts older than 5 min → stale (alerts suppressed downstream)


@dataclass
class ProcessResult:
    """Outcome of one position update, for the endpoint response and tests."""

    stored: bool
    reason: str | None = None           # set when stored is False
    stale: bool = False
    device_id: uuid.UUID | None = None
    child_id: uuid.UUID | None = None
    lat: float | None = None            # for the off-hot-path geofence breach check
    lng: float | None = None
    battery: int | None = None          # percent, for the off-hot-path battery check
    speed: float | None = None          # km/h, for the off-hot-path speed check
    # The child "latest" payload, reused for the off-hot-path Firebase live write.
    live_payload: dict | None = None


def _coords_valid(lat: float, lng: float) -> bool:
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
        return False
    # Reject the "null island" (0, 0) — a classic no-fix sentinel from GPS devices.
    if lat == 0.0 and lng == 0.0:
        return False
    return True


class LocationService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis

    # ------------------------------------------------------------------ public
    async def process_update(self, body: TraccarForward) -> ProcessResult:
        pos = body.position
        unique_id = body.device.unique_id if body.device else None

        resolved = await self._resolve_device(pos.device_id, unique_id)
        if resolved is None:
            return ProcessResult(stored=False, reason="unknown_device")
        device_id, child_id = resolved

        if not pos.valid or not _coords_valid(pos.latitude, pos.longitude):
            return ProcessResult(stored=False, reason="invalid_coordinates")

        now = datetime.now(timezone.utc)
        ts = pos.best_time or now
        stale = (now - ts).total_seconds() > STALE_AFTER_SECONDS

        live_payload = await self._write_cache(device_id, child_id, pos, ts)
        await self.redis.set(rk.device_online(device_id), "1", ex=rk.ONLINE_TTL)
        # lastseen = receipt time (not fix time) — drives offline detection.
        await self.redis.set(
            rk.device_lastseen(device_id), str(now.timestamp()), ex=rk.LASTSEEN_TTL
        )
        await self._enqueue_batch(device_id, child_id, pos, ts)

        return ProcessResult(
            stored=True, stale=stale, device_id=device_id, child_id=child_id,
            lat=pos.latitude, lng=pos.longitude,
            battery=pos.battery_pct, speed=pos.speed_kmh, live_payload=live_payload,
        )

    async def resolve_device(
        self, traccar_id: int, unique_id: str | None
    ) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Public device→(device_id, child_id) resolution (Redis-cached), reused by
        the SOS alarm webhook."""
        return await self._resolve_device(traccar_id, unique_id)

    # --------------------------------------------------------------- internals
    async def _resolve_device(
        self, traccar_id: int, unique_id: str | None
    ) -> tuple[uuid.UUID, uuid.UUID] | None:
        """traccar_id (or IMEI fallback) → (device_id, child_id), Redis-cached 1h."""
        cache_key = rk.traccar_device_map(traccar_id)
        cached = await self.redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return uuid.UUID(data["device_id"]), uuid.UUID(data["child_id"])

        device = await self._lookup_device(traccar_id, unique_id)
        if device is None:
            return None

        await self.redis.set(
            cache_key,
            json.dumps({"device_id": str(device.id), "child_id": str(device.child_id)}),
            ex=rk.TRACCAR_MAP_TTL,
        )
        return device.id, device.child_id

    async def _lookup_device(self, traccar_id: int, unique_id: str | None) -> Device | None:
        stmt = select(Device).where(
            Device.traccar_id == traccar_id, Device.deleted_at.is_(None)
        )
        device = (await self.db.execute(stmt)).scalar_one_or_none()
        if device is None and unique_id:
            # Fallback: device paired but traccar_id not yet stored — match on IMEI.
            stmt = select(Device).where(
                Device.imei == unique_id, Device.deleted_at.is_(None)
            )
            device = (await self.db.execute(stmt)).scalar_one_or_none()
        return device

    async def _write_cache(
        self,
        device_id: uuid.UUID,
        child_id: uuid.UUID,
        pos: TraccarPositionIn,
        ts: datetime,
    ) -> dict:
        """Write the child + device latest caches. Returns the child payload, which
        is reused verbatim for the Firebase live-map write (kept consistent)."""
        ts_iso = ts.isoformat()

        child_payload = {
            "lat": pos.latitude,
            "lng": pos.longitude,
            "device_id": str(device_id),
            "battery": pos.battery_pct,
            "speed": pos.speed_kmh,
            "accuracy": pos.accuracy,
            "bearing": pos.course,
            "is_moving": pos.attributes.motion,
            "ts": ts_iso,
        }
        device_payload = {
            "lat": pos.latitude,
            "lng": pos.longitude,
            "battery": pos.battery_pct,
            "ts": ts_iso,
        }
        await self.redis.set(
            rk.loc_child_latest(child_id), json.dumps(child_payload), ex=rk.LOCATION_CACHE_TTL
        )
        await self.redis.set(
            rk.loc_device_latest(device_id), json.dumps(device_payload), ex=rk.LOCATION_CACHE_TTL
        )
        return child_payload

    async def _enqueue_batch(
        self,
        device_id: uuid.UUID,
        child_id: uuid.UUID,
        pos: TraccarPositionIn,
        ts: datetime,
    ) -> None:
        """Buffer a row for the 5s batch writer to bulk-INSERT into `locations`."""
        row = {
            "device_id": str(device_id),
            "child_id": str(child_id),
            "lat": pos.latitude,
            "lng": pos.longitude,
            "accuracy": pos.accuracy,
            "speed": pos.speed_kmh,
            "altitude": pos.altitude,
            "bearing": pos.course,
            "battery": pos.battery_pct,
            "is_moving": pos.attributes.motion,
            "address": pos.address,
            "timestamp": ts.isoformat(),
        }
        await self.redis.lpush(rk.BATCH_LOCATIONS, json.dumps(row))
