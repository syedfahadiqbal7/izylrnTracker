"""SOS emergency handling — Flow C (CLAUDE.md §5, decisions §3.6/§3.11).

Two services, split like the geofence pair (request-path CRUD vs. background engine):
  * ``SosAlarmService`` — runs in the alarm-webhook BackgroundTask; creates the SOS.
  * ``SosService`` — request-path read/resolve API (Slice 2).

``SosAlarmService.trigger_from_alarm`` is idempotent per active episode: **one active
SOS per child** is enforced by the `uq_sos_one_active_per_child` partial unique index,
with a Redis `sos:{child}:active` fast-path + a DB pre-check for dedup (Decision B).
On a genuine trigger it:
  1. INSERTs an `sos_events` row (status='active'),
  2. inserts one `alerts` inbox row per family member + sends an **urgent** FCM
     (MAX priority, bypasses DND/School Mode — Decision C) via `AlertService`,
  3. writes the Firebase `sos/{child}` node the parent app streams,
  4. sets the Redis active marker (cleared on resolve).

Location (Decision E): the alarm's own coordinates are used when valid; otherwise we
fall back to the last-known Redis location and flag the event `approximate=true`.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.errors import APIException
from app.models.child import Child, FamilyMember
from app.models.sos import EmergencyContact, SosEvent
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.fcm_gateway import FcmGateway
from app.services.location_service import _coords_valid
from app.services.realtime_gateway import RealtimeGateway

logger = logging.getLogger("izysafe.sos")


class SosAlarmService:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        redis: Redis,
        realtime: RealtimeGateway,
        fcm: FcmGateway,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.realtime = realtime
        self.fcm = fcm

    async def trigger_from_alarm(
        self,
        child_id: uuid.UUID,
        device_id: uuid.UUID | None,
        lat: float | None = None,
        lng: float | None = None,
        address: str | None = None,
    ) -> uuid.UUID | None:
        """Create an active SOS (deduped) and fan it out. Returns the new sos_id, or
        None when deduped / the child is gone."""
        if await self.redis.get(rk.sos_active(child_id)):
            return None  # already active — dedup fast path

        lat, lng, approximate = await self._resolve_location(child_id, lat, lng)
        triggered_at = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            # Pre-check the partial-unique invariant (one active SOS per child).
            active = (
                await session.execute(
                    select(SosEvent.id).where(
                        SosEvent.child_id == child_id, SosEvent.status == "active"
                    )
                )
            ).first()
            if active is not None:
                return None

            child = await session.get(Child, child_id)
            if child is None or child.deleted_at is not None:
                return None

            sos = SosEvent(
                child_id=child_id, device_id=device_id, lat=lat, lng=lng,
                address=address, approximate=approximate, status="active",
                triggered_at=triggered_at,
            )
            session.add(sos)
            try:
                await session.flush()  # RETURNING id + the unique index fires here
            except IntegrityError:
                await session.rollback()
                return None  # raced another alarm → that one wins
            sos_id = sos.id

            title = "🚨 SOS Alert"
            body = f"{child.name} triggered an emergency SOS."
            data = {"sos_id": str(sos_id), "lat": lat, "lng": lng, "approximate": approximate}
            await AlertService(session, self.fcm).notify_family(
                child_id, "sos", title, body, data, urgent=True
            )
            # Fan out an urgent push to app-user emergency contacts (Decision D).
            ec_tokens = await self._emergency_contact_tokens(session, child_id)
            if ec_tokens:
                await self.fcm.send(ec_tokens, title, body, {**data, "type": "sos"}, urgent=True)
            await session.commit()

        await self.redis.set(rk.sos_active(child_id), "1")  # until resolved (Slice 2)
        await self.realtime.set_sos(
            str(child_id),
            {
                "active": True,
                "sos_id": str(sos_id),
                "lat": lat,
                "lng": lng,
                "approximate": approximate,
                "triggered_at": triggered_at.isoformat(),
            },
        )
        logger.info("SOS triggered for child %s (sos_id=%s)", child_id, sos_id)
        return sos_id

    async def _emergency_contact_tokens(
        self, session: AsyncSession, child_id: uuid.UUID
    ) -> list[str]:
        """FCM tokens of app-user emergency contacts for this child, EXCLUDING family
        members (who were already notified via notify_family) so nobody is double-pushed.
        Matched by phone — robust even if a contact registered after being added."""
        family_user_ids = select(FamilyMember.user_id).where(
            FamilyMember.child_id == child_id
        )
        rows = (
            await session.execute(
                select(User.fcm_token)
                .join(EmergencyContact, EmergencyContact.phone == User.phone)
                .where(
                    EmergencyContact.child_id == child_id,
                    User.fcm_token.is_not(None),
                    User.deleted_at.is_(None),
                    User.id.not_in(family_user_ids),
                )
            )
        ).scalars().all()
        return list({t for t in rows if t})  # dedup tokens

    async def _resolve_location(
        self, child_id: uuid.UUID, lat: float | None, lng: float | None
    ) -> tuple[float | None, float | None, bool]:
        """Prefer the alarm's own fix; else fall back to the last-known Redis location
        (flagged approximate). Returns (lat, lng, approximate)."""
        if lat is not None and lng is not None and _coords_valid(lat, lng):
            return lat, lng, False
        cached = await self.redis.get(rk.loc_child_latest(child_id))
        if cached:
            data = json.loads(cached)
            return data.get("lat"), data.get("lng"), True
        return None, None, True


class SosService:
    """Request-path SOS read/resolve API (Slice 2). Family-scoped via family_members:
    a non-member sees nothing and gets 404 (never reveals existence)."""

    def __init__(self, db: AsyncSession, redis: Redis, realtime: RealtimeGateway) -> None:
        self.db = db
        self.redis = redis
        self.realtime = realtime

    async def list_active(self, user) -> list[tuple[SosEvent, str]]:
        """Active SOS events across all of the user's children (newest first)."""
        rows = (
            await self.db.execute(
                select(SosEvent, Child.name)
                .join(Child, Child.id == SosEvent.child_id)
                .join(FamilyMember, FamilyMember.child_id == SosEvent.child_id)
                .where(
                    SosEvent.status == "active",
                    FamilyMember.user_id == user.id,
                    Child.deleted_at.is_(None),
                )
                .order_by(SosEvent.triggered_at.desc())
            )
        ).all()
        return [(sos, name) for sos, name in rows]

    async def resolve(self, user, sos_id: uuid.UUID) -> tuple[SosEvent, str]:
        """Resolve an SOS (any family member — Decision F). Idempotent: re-resolving
        an already-resolved event is a no-op. Clears the Firebase active flag + the
        Redis marker so every parent's modal dismisses together."""
        row = (
            await self.db.execute(
                select(SosEvent, Child.name)
                .join(Child, Child.id == SosEvent.child_id)
                .join(FamilyMember, FamilyMember.child_id == SosEvent.child_id)
                .where(SosEvent.id == sos_id, FamilyMember.user_id == user.id)
            )
        ).first()
        if row is None:
            raise APIException(404, "SOS_NOT_FOUND", "SOS not found")
        sos, child_name = row

        if sos.status == "active":
            sos.status = "resolved"
            sos.resolved_at = datetime.now(timezone.utc)
            sos.resolved_by = user.id
            await self.db.commit()
            await self.db.refresh(sos)
            await self.redis.delete(rk.sos_active(sos.child_id))
            await self.realtime.clear_sos(str(sos.child_id))
            logger.info("SOS %s resolved by user %s", sos_id, user.id)
        return sos, child_name
