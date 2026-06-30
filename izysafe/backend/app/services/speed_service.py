"""Speed alerts — a per-position check kept off the request hot path (§4).

Runs in a webhook BackgroundTask, but only when speed clears the lowest possible
threshold (see MIN_ALERT_SPEED_KMH) so walking/stationary pings never touch the DB.

Gating: the child must have `speed_alert_enabled` AND the primary parent must be
on a Basic+ tier (Speed Alert is Basic+, CLAUDE.md §10).

Anti-spike: a single GPS spike won't fire — we require `speed_required_samples`
(3) over-threshold readings within a sliding `speed_window_seconds` (90s) window
(`speed_count:{child}`). A reading at/below threshold resets the counter. After
firing, a `speed_alerted:{child}` debounce (10 min) suppresses repeats.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.models.child import Child, FamilyMember
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.children_service import effective_tier
from app.services.fcm_gateway import FcmGateway

logger = logging.getLogger("izysafe.speed")

# Speed Alert is Basic+ (free tier excluded).
ALLOWED_TIERS = {"basic", "premium", "school"}
# Lowest configurable child threshold (speed_threshold_kmh IN (20,30,...)). A speed
# at/below this can never exceed any threshold, so the webhook skips the check —
# keep in sync with the model's CHECK constraint.
MIN_ALERT_SPEED_KMH = 20


class SpeedService:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        redis: Redis,
        fcm: FcmGateway,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.fcm = fcm

    async def evaluate(self, child_id: uuid.UUID, speed_kmh: float) -> None:
        if speed_kmh is None:
            return

        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(Child, User)
                    .join(FamilyMember, FamilyMember.child_id == Child.id)
                    .join(User, User.id == FamilyMember.user_id)
                    .where(
                        Child.id == child_id,
                        FamilyMember.is_primary.is_(True),
                        Child.deleted_at.is_(None),
                    )
                )
            ).first()
            if row is None:
                return
            child, primary = row

            # Gating: per-child toggle + Basic+ tier on the primary parent.
            if not child.speed_alert_enabled or effective_tier(primary) not in ALLOWED_TIERS:
                return

            if speed_kmh <= child.speed_threshold_kmh:
                await self.redis.delete(rk.speed_count(child_id))  # not speeding → reset
                return

            count = await self.redis.incr(rk.speed_count(child_id))
            await self.redis.expire(rk.speed_count(child_id), settings.speed_window_seconds)
            if count < settings.speed_required_samples:
                return  # not yet sustained
            if await self.redis.get(rk.speed_alerted(child_id)):
                return  # debounced

            await AlertService(session, self.fcm).notify_family(
                child_id,
                "speed",
                "Speed alert",
                f"{child.name} is moving at {int(speed_kmh)} km/h.",
                {"speed": int(speed_kmh), "threshold": child.speed_threshold_kmh},
            )
            await session.commit()

        await self.redis.set(
            rk.speed_alerted(child_id), "1", ex=settings.speed_alert_cooldown_seconds
        )
        logger.info("Speed alert for child %s (%d km/h)", child_id, int(speed_kmh))
