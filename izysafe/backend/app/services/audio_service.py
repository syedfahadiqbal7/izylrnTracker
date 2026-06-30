"""Audio request-path services: Sound Around (F11) + Two-way Call (F12).

Both features work the same way (CLAUDE.md §3.12 — **no media server**): the backend
issues a SIM command to the child's watch via Traccar, and the watch then dials the
requesting parent over its own SIM. `MONITOR,<phone>#` = silent ambient listen (Sound
Around); `CALLBACK,<phone>#` = duplex call (Two-way Call). The backend's job is to
**gate, issue, and log** — the audio never touches our servers, and the call's actual
outcome (answer / duration / miss) is **not observable** here.

Shared gate stack (`_AudioFeatureService`, cheapest first):
  1. **Authorization** — caller must be a family member with ``can_call`` (else 404/403).
  2. **Tier** — both are Basic+, counted over the child's **primary parent**; Free → 402.
  3. **Watch online** — a paired watch with a Traccar id, currently online in Redis
     (`device:{id}:online`); else 404 (no watch) / 409 (offline).

Per-feature extras:
  * Sound Around — daily quota (`sound_around_daily_limit`/child/day, `sound_sessions:{child}`,
    midnight TTL in the primary parent's tz), consumed only on a successful dispatch.
  * Two-way Call — a no-active-call guard via the Redis `call:{child}:active` marker (TTL
    `two_way_call_active_seconds`); since the call's end isn't observable, the marker is
    time-bounded rather than cleared on hang-up.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.errors import APIException
from app.models.child import Child, FamilyMember
from app.models.comms import AudioSession, CallRecord
from app.models.device import Device
from app.models.user import User
from app.services.children_service import effective_tier
from app.services.traccar_gateway import TraccarGateway

logger = logging.getLogger("izysafe.audio")

# Sound Around + Two-way Call are Basic+ features (Premium + School inherit them).
AUDIO_TIERS = {"basic", "premium", "school"}


class _AudioFeatureService:
    """Shared gates for the audio features (can_call → tier → watch online)."""

    # Subclasses set the tier-gate error (both are Basic+, but the codes differ).
    REQUIRES_TIER_CODE = "AUDIO_REQUIRES_BASIC"
    REQUIRES_TIER_MSG = "Upgrade to Basic plan to use this feature"

    def __init__(self, db: AsyncSession, redis: Redis, traccar: TraccarGateway) -> None:
        self.db = db
        self.redis = redis
        self.traccar = traccar

    async def _require_can_call(self, user_id: uuid.UUID, child_id: uuid.UUID) -> FamilyMember:
        """Caller must be a (non-deleted child) family member; 404 if not a member
        (never reveal the child exists), 403 if a member without ``can_call``."""
        row = (
            await self.db.execute(
                select(FamilyMember)
                .join(Child, Child.id == FamilyMember.child_id)
                .where(
                    FamilyMember.child_id == child_id,
                    FamilyMember.user_id == user_id,
                    Child.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise APIException(404, "CHILD_NOT_FOUND", "Child not found")
        if not row.can_call:
            raise APIException(403, "FORBIDDEN", "You don't have permission to call this child")
        return row

    def _enforce_tier(self, tier: str) -> None:
        if tier not in AUDIO_TIERS:
            raise APIException(402, self.REQUIRES_TIER_CODE, self.REQUIRES_TIER_MSG)

    async def _online_watch(self, child_id: uuid.UUID) -> Device:
        """The child's commandable, currently-online watch. 404 if no watch is paired,
        409 if one exists but isn't online (audio needs a live watch)."""
        watches = (
            await self.db.execute(
                select(Device).where(
                    Device.child_id == child_id,
                    Device.device_type == "watch",
                    Device.active.is_(True),
                    Device.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        if not watches:
            raise APIException(404, "NO_WATCH", "No watch is paired for this child")
        for device in watches:
            if device.traccar_id is None:
                continue
            if await self.redis.get(rk.device_online(device.id)):
                return device
        raise APIException(
            409, "WATCH_OFFLINE", "The watch is offline — this needs the watch online"
        )

    async def _primary_parent(self, child_id: uuid.UUID) -> User | None:
        return (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .where(FamilyMember.child_id == child_id, FamilyMember.is_primary.is_(True))
            )
        ).scalars().first()


class SoundAroundService(_AudioFeatureService):
    REQUIRES_TIER_CODE = "SOUND_AROUND_REQUIRES_BASIC"
    REQUIRES_TIER_MSG = "Upgrade to Basic plan to use Sound Around"

    async def start(self, user: User, child_id: uuid.UUID) -> AudioSession:
        """Run the gates, issue the MONITOR command, log an audio_sessions row.
        Returns the persisted session. The watch dials the requesting user's phone."""
        await self._require_can_call(user.id, child_id)

        primary = await self._primary_parent(child_id)
        self._enforce_tier(effective_tier(primary) if primary else "free")

        device = await self._online_watch(child_id)
        await self._check_quota(child_id)

        ok = await self.traccar.sound_around(device.traccar_id, user.phone)
        if not ok:
            raise APIException(
                502, "SOUND_AROUND_DISPATCH_FAILED",
                "Couldn't reach the watch right now — please try again",
            )

        await self._consume_quota(child_id, primary)
        session = AudioSession(child_id=child_id, device_id=device.id, user_id=user.id)
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info("Sound Around started for child %s by user %s", child_id, user.id)
        return session

    async def _check_quota(self, child_id: uuid.UUID) -> None:
        used = await self.redis.get(rk.sound_sessions(child_id))
        if used is not None and int(used) >= settings.sound_around_daily_limit:
            raise APIException(
                429, "SOUND_AROUND_LIMIT_REACHED",
                f"Daily Sound Around limit reached ({settings.sound_around_daily_limit} per day)",
            )

    async def _consume_quota(self, child_id: uuid.UUID, primary: User | None) -> None:
        """Increment the daily counter; on the first use of the day set it to expire at
        the next midnight in the primary parent's timezone."""
        key = rk.sound_sessions(child_id)
        count = await self.redis.incr(key)
        if count == 1:
            tz_name = primary.timezone if primary else "UTC"
            await self.redis.expire(key, _seconds_until_midnight(tz_name))


class TwoWayCallService(_AudioFeatureService):
    REQUIRES_TIER_CODE = "TWO_WAY_CALL_REQUIRES_BASIC"
    REQUIRES_TIER_MSG = "Upgrade to Basic plan to use Two-way Call"

    async def start(self, user: User, child_id: uuid.UUID) -> CallRecord:
        """Run the gates + no-active-call guard, issue the CALLBACK command, log a
        call_records row (status='initiated'). The watch dials the requesting user's
        phone. Outcome (answer/duration/miss) isn't observable here, so the row stays
        'initiated' and concurrency is bounded by the time-limited Redis marker."""
        await self._require_can_call(user.id, child_id)

        primary = await self._primary_parent(child_id)
        self._enforce_tier(effective_tier(primary) if primary else "free")

        device = await self._online_watch(child_id)

        if await self.redis.get(rk.call_active(child_id)):
            raise APIException(
                409, "CALL_IN_PROGRESS", "A call is already in progress for this child"
            )

        ok = await self.traccar.two_way_call(device.traccar_id, user.phone)
        if not ok:
            raise APIException(
                502, "TWO_WAY_CALL_DISPATCH_FAILED",
                "Couldn't reach the watch right now — please try again",
            )

        # Mark the call in-progress for a bounded window (no hang-up signal exists).
        await self.redis.set(
            rk.call_active(child_id), "1", ex=settings.two_way_call_active_seconds
        )
        record = CallRecord(
            child_id=child_id, device_id=device.id, initiated_by=user.id, status="initiated"
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        logger.info("Two-way Call started for child %s by user %s", child_id, user.id)
        return record


def _seconds_until_midnight(tz_name: str) -> int:
    """Seconds from now until the next local midnight in `tz_name` (falls back to UTC
    for an unknown zone). Always ≥ 1 so the Redis key can't be set to expire instantly."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = UTC
    now = datetime.now(tz)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))
