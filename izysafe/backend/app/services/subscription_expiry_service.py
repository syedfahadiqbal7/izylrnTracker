"""Subscription expiry sweep (Sprint 6 Slice 4) — a daily Celery-beat job.

`effective_tier` already treats a lapsed paid tier as free on the read path, so gating is
safe even before the sweep runs. The sweep makes the downgrade **durable**: it flips the
`users` row to free and marks the `subscriptions` row 'expired', then notifies the user so
they can renew. Non-destructive (Decision E) — it never deletes children/zones/etc.; the
user simply can't create new over-limit resources once free.

Runs in a Celery worker via its own `session_factory` (mirrors the background-task /
lifespan-loop services); the request session is irrelevant here.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Subscription, User
from app.services.alert_service import AlertService
from app.services.fcm_gateway import FcmGateway

logger = logging.getLogger("izysafe.jobs.expiry")


class SubscriptionExpiryService:
    def __init__(
        self, session_factory: Callable[[], AsyncSession], fcm: FcmGateway
    ) -> None:
        self.session_factory = session_factory
        self.fcm = fcm

    async def run(self, now: datetime | None = None) -> int:
        """Downgrade every user whose paid tier has lapsed. Returns the count downgraded."""
        now = now or datetime.now(UTC)
        async with self.session_factory() as session:
            users = (
                await session.execute(
                    select(User).where(
                        User.subscription_tier != "free",
                        User.subscription_expires_at.is_not(None),
                        User.subscription_expires_at < now,
                        User.deleted_at.is_(None),
                    )
                )
            ).scalars().all()

            for user in users:
                lapsed_tier = user.subscription_tier
                user.subscription_tier = "free"
                await self._expire_rows(session, user.id, now)
                await AlertService(session, self.fcm).notify_user(
                    user.id, "system", "Subscription expired",
                    f"Your {lapsed_tier.title()} plan has expired. Renew to restore your features.",
                    data={"kind": "subscription", "event": "expired"},
                )

            await session.commit()
            if users:
                logger.info("Expiry sweep downgraded %d user(s)", len(users))
            return len(users)

    async def _expire_rows(
        self, session: AsyncSession, user_id: uuid.UUID, now: datetime
    ) -> None:
        """Mark the user's still-live subscription rows 'expired' (audit trail)."""
        await session.execute(
            update(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status.in_(("active", "past_due", "cancelled")),
                Subscription.expires_at < now,
            )
            .values(status="expired")
        )
