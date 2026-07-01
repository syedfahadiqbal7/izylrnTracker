"""Watch Removed detection (Sprint 7 Slice 4, F18).

The watch's anti-tamper sensor fires a Traccar alarm (e.g. `tamper`/`removing`) when
it's taken off the wrist (Decision D13 — the exact GT06 string is validated on the
hardware spike). We don't alert immediately: a brief removal (adjusting the strap)
shouldn't nag. Instead:

  * `mark_removed` (alarm-webhook BackgroundTask) records `watch_removed:{device}:since`
    = now the FIRST time in an episode (SET NX, so repeated tamper alarms don't reset
    the timer) and adds the device to the `watch_removed:pending` set — but only if the
    device has the feature enabled AND the primary parent is Basic+ (CLAUDE.md §10).
  * `sweep_once` (reused DeviceStatusMonitor 60s loop — Decision D14) fires one
    `watch_removed` alert per episode once now − since ≥ the device's
    `watch_removed_threshold_min` (5/10/15), then drops it from the pending set so it
    can't re-fire.
  * `mark_worn` (a re-wear alarm, if the model emits one) clears the state so the next
    removal starts a fresh episode.

There is no `watch_removed_events` ledger table — the alert inbox row is the record.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.models.child import FamilyMember
from app.models.device import Device
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.children_service import effective_tier
from app.services.fcm_gateway import FcmGateway

logger = logging.getLogger("izysafe.watch_removed")

# Watch Removed is a Basic+ feature (School inherits it).
WATCH_REMOVED_TIERS = {"basic", "premium", "school"}


class WatchRemovedService:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        redis: Redis,
        fcm: FcmGateway,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.fcm = fcm

    # --------------------------------------------------------------- ingest
    async def mark_removed(self, device_id: uuid.UUID, child_id: uuid.UUID) -> None:
        """Record the start of a removal episode (gated on enabled + Basic+)."""
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(Device, User)
                    .join(
                        FamilyMember,
                        (FamilyMember.child_id == Device.child_id)
                        & (FamilyMember.is_primary.is_(True)),
                    )
                    .join(User, User.id == FamilyMember.user_id)
                    .where(Device.id == device_id, Device.deleted_at.is_(None))
                )
            ).first()
        if row is None:
            return
        device, parent = row
        if not device.watch_removed_enabled:
            return
        if effective_tier(parent) not in WATCH_REMOVED_TIERS:
            return

        # SET NX: only the first alarm of an episode stamps `since` (so duplicates don't
        # reset the timer). Add to the pending set only on that fresh stamp, so a repeat
        # alarm after a fire can't re-queue and double-alert.
        is_new = await self.redis.set(
            rk.watch_removed_since(device_id), time.time(),
            nx=True, ex=rk.WATCH_REMOVED_SINCE_TTL,
        )
        if is_new:
            await self.redis.sadd(rk.WATCH_REMOVED_PENDING, str(device_id))
            logger.info("Watch removal episode started for device %s", device_id)

    async def mark_worn(self, device_id: uuid.UUID) -> None:
        """Clear a removal episode on a re-wear signal."""
        await self.redis.delete(rk.watch_removed_since(device_id))
        await self.redis.srem(rk.WATCH_REMOVED_PENDING, str(device_id))
        logger.info("Watch worn again — cleared removal episode for device %s", device_id)

    # ---------------------------------------------------------------- sweep
    async def sweep_once(self) -> int:
        """Fire `watch_removed` for devices past their threshold. Returns count fired."""
        members = await self.redis.smembers(rk.WATCH_REMOVED_PENDING)
        if not members:
            return 0

        now = time.time()
        ids = {uuid.UUID(m) for m in members}
        async with self.session_factory() as session:
            devices = {
                d.id: d
                for d in (
                    await session.execute(
                        select(Device).where(
                            Device.id.in_(ids),
                            Device.deleted_at.is_(None),
                            Device.watch_removed_enabled.is_(True),
                        )
                    )
                ).scalars().all()
            }

            fired = 0
            alerts = AlertService(session, self.fcm)
            for member in members:
                device = devices.get(uuid.UUID(member))
                since = await self.redis.get(rk.watch_removed_since(uuid.UUID(member)))
                # Gone, feature-off, or expired stamp → drop the stale pending entry.
                if device is None or since is None:
                    await self.redis.srem(rk.WATCH_REMOVED_PENDING, member)
                    continue
                if (now - float(since)) < device.watch_removed_threshold_min * 60:
                    continue

                minutes = device.watch_removed_threshold_min
                await alerts.notify_family(
                    device.child_id,
                    "watch_removed",
                    "Watch removed",
                    f"{device.name} may have been taken off — no wrist contact for {minutes} minutes.",
                    {"device_id": str(device.id)},
                )
                # Episode handled: drop from pending so it can't re-fire (the `since`
                # stamp lingers until a re-wear or its 24h TTL, blocking a duplicate).
                await self.redis.srem(rk.WATCH_REMOVED_PENDING, member)
                fired += 1

            if fired:
                await session.commit()
        if fired:
            logger.info("Watch-removed sweep: %d device(s) alerted.", fired)
        return fired
