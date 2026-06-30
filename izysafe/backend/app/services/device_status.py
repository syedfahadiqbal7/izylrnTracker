"""Device online/offline status — the state machine of Flow A.

Two halves, kept off the request hot path (CLAUDE.md §4):

* `DeviceStatusService.reconcile_online` — runs in a webhook BackgroundTask. A
  position means the device is communicating, so it flips `is_online` True (and
  updates `last_seen_at`) on the *transition* only. The `device:{id}:status` Redis
  marker short-circuits the common case (already online) without a DB read.

* `DeviceStatusMonitor` — a lifespan sweep loop (every `interval`s). It finds
  online devices whose last *received* position (`device:{id}:lastseen`) is older
  than `offline_threshold` (15 min), flips them offline, and fires one
  `device_offline` alert per episode (the True→False transition is the dedupe).

The 5-min `device:{id}:online` key (set on the hot path) is the separate sub-second
"live right now" indicator; this state machine is the coarser connected/alert view.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.models.device import Device
from app.services.alert_service import AlertService
from app.services.fcm_gateway import FcmGateway

logger = logging.getLogger("izysafe.device_status")


class DeviceStatusService:
    """Online-transition reconciliation (webhook BackgroundTask)."""

    def __init__(self, session_factory: Callable[[], AsyncSession], redis: Redis) -> None:
        self.session_factory = session_factory
        self.redis = redis

    async def reconcile_online(self, device_id: uuid.UUID) -> bool:
        """If the device isn't already marked online, flip it (transition). Returns
        True when a transition was persisted."""
        try:
            if await self.redis.get(rk.device_status(device_id)) == "online":
                return False  # fast path — already online, no DB touch
        except RedisError:
            pass  # Redis blip — fall through and let the DB be the source of truth

        async with self.session_factory() as session:
            result = await session.execute(
                update(Device)
                .where(
                    Device.id == device_id,
                    Device.deleted_at.is_(None),
                    Device.is_online.is_(False),
                )
                .values(is_online=True, last_seen_at=datetime.now(timezone.utc))
            )
            await session.commit()
            transitioned = result.rowcount > 0

        try:
            await self.redis.set(rk.device_status(device_id), "online", ex=rk.STATUS_TTL)
        except RedisError:
            logger.warning("Could not set status marker for device %s", device_id)
        return transitioned


class DeviceStatusMonitor:
    """Offline-detection sweep loop (FastAPI lifespan task)."""

    def __init__(
        self,
        redis: Redis,
        session_factory: Callable[[], AsyncSession],
        fcm: FcmGateway,
        offline_threshold: int = settings.device_offline_threshold_seconds,
        interval: int = settings.device_sweep_interval_seconds,
    ) -> None:
        self.redis = redis
        self.session_factory = session_factory
        self.fcm = fcm
        self.offline_threshold = offline_threshold
        self.interval = interval
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="device-status-monitor")
        logger.info(
            "Device status monitor started (offline>%ds, sweep=%ds).",
            self.offline_threshold, self.interval,
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        logger.info("Device status monitor stopped.")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass
            else:
                break  # stop signalled
            try:
                await self.sweep_once()
            except Exception:  # never let one bad sweep kill the loop
                logger.exception("Device status sweep failed")

    # ----------------------------------------------------------------- sweep
    async def sweep_once(self) -> int:
        """Flip stale online devices to offline + alert. Returns count flipped."""
        now = time.time()
        async with self.session_factory() as session:
            devices = (
                await session.execute(
                    select(Device).where(
                        Device.is_online.is_(True), Device.deleted_at.is_(None)
                    )
                )
            ).scalars().all()

            flipped = 0
            alerts = AlertService(session, self.fcm)
            for device in devices:
                if not await self._is_offline(device.id, now):
                    continue
                device.is_online = False
                flipped += 1
                await self.redis.set(rk.device_status(device.id), "offline", ex=rk.STATUS_TTL)
                minutes = self.offline_threshold // 60
                await alerts.notify_family(
                    device.child_id,
                    "device_offline",
                    "Device offline",
                    f"{device.name} hasn't sent a location in {minutes} minutes.",
                    {"device_id": str(device.id)},
                )

            if flipped:
                await session.commit()
        if flipped:
            logger.info("Device status sweep: %d device(s) → offline.", flipped)
        return flipped

    async def _is_offline(self, device_id: uuid.UUID, now: float) -> bool:
        last = await self.redis.get(rk.device_lastseen(device_id))
        if last is None:
            return True  # no recent receipt on record → treat as offline
        return (now - float(last)) >= self.offline_threshold
