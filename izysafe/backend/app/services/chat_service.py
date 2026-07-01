"""Chat (Sprint 7 Slice 6, F23) — short two-way text between a parent and the watch.

Basic+ (CLAUDE.md §10), counted over the child's primary parent. Two directions, split
like the SOS request/background pair:

  * ``ChatService`` (request path) — `send` stores a parent→watch message and makes a
    best-effort dispatch to the watch via a Traccar SIM command; `list` returns history.
    Unlike audio, a send never fails on an offline watch: the row is always stored and
    just stays `queued` until re-dispatch (which, like the watch's own text delivery, is
    part of the pending hardware spike — Decision D17). A successful dispatch → `sent`.
    We never set `delivered` (the watch gives no ack — mirrors the audio outcome gap).

  * ``ChatInboundService`` (alarm/message-webhook BackgroundTask) — `receive` stores a
    watch→parent message and fans a `chat_reply` alert out to the family via AlertService.

Dispatch + inbound transport are GT06-model-specific and UNVALIDATED end-to-end
(docs/HARDWARE_SPIKE.md); only the command/parse plumbing is built here.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIException
from app.models.child import Child, FamilyMember
from app.models.comms import ChatMessage
from app.models.device import Device
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.children_service import effective_tier
from app.services.fcm_gateway import FcmGateway
from app.services.traccar_gateway import TraccarGateway

logger = logging.getLogger("izysafe.chat")

# Chat is a Basic+ feature (Premium + School inherit it).
CHAT_TIERS = {"basic", "premium", "school"}


class ChatService:
    """Request-path chat: send (parent→watch) + history."""

    def __init__(self, db: AsyncSession, redis: Redis, traccar: TraccarGateway) -> None:
        self.db = db
        self.redis = redis
        self.traccar = traccar

    async def send(self, user, child_id: uuid.UUID, content: str) -> ChatMessage:
        await self._require_member(user.id, child_id)
        self._enforce_tier(await self._child_tier(child_id))

        message = ChatMessage(
            child_id=child_id, sender_type="parent", sender_id=user.id,
            content=content, status="queued",
        )
        self.db.add(message)
        await self.db.flush()

        # Best-effort dispatch — a `sent` status means Traccar accepted the command, not
        # that the watch displayed it (no ack exists). Offline / no watch → stays queued.
        if await self._dispatch(child_id, content):
            message.status = "sent"
        await self.db.commit()
        await self.db.refresh(message)
        logger.info("Chat %s → child %s (status=%s)", message.id, child_id, message.status)
        return message

    async def list(
        self, user, child_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[ChatMessage], int]:
        await self._require_member(user.id, child_id)
        total = (
            await self.db.execute(
                select(func.count()).select_from(ChatMessage).where(
                    ChatMessage.child_id == child_id
                )
            )
        ).scalar_one()
        rows = (
            await self.db.execute(
                select(ChatMessage)
                .where(ChatMessage.child_id == child_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), total

    # ---------------------------------------------------------------- helpers
    async def _dispatch(self, child_id: uuid.UUID, content: str) -> bool:
        """Push the text to the child's first online watch. Best-effort — never raises."""
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
        from app.core import redis_keys as rk

        for device in watches:
            if device.traccar_id is None:
                continue
            if await self.redis.get(rk.device_online(device.id)):
                return await self.traccar.send_text(device.traccar_id, content)
        return False

    async def _require_member(self, user_id: uuid.UUID, child_id: uuid.UUID) -> FamilyMember:
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
        if not row.can_view:
            raise APIException(403, "FORBIDDEN", "You don't have permission to message this child")
        return row

    def _enforce_tier(self, tier: str) -> None:
        if tier not in CHAT_TIERS:
            raise APIException(402, "CHAT_REQUIRES_BASIC", "Upgrade to Basic plan to use chat")

    async def _child_tier(self, child_id: uuid.UUID) -> str:
        primary = (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .where(FamilyMember.child_id == child_id, FamilyMember.is_primary.is_(True))
            )
        ).scalars().first()
        return effective_tier(primary) if primary else "free"


class ChatInboundService:
    """Background inbound chat: store a watch→parent message + notify the family."""

    def __init__(
        self, session_factory: Callable[[], AsyncSession], fcm: FcmGateway
    ) -> None:
        self.session_factory = session_factory
        self.fcm = fcm

    async def receive(
        self, device_id: uuid.UUID, child_id: uuid.UUID, content: str
    ) -> None:
        async with self.session_factory() as session:
            # Gate on the primary parent's tier — inbound chat is Basic+ too.
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
            child, parent = row
            if effective_tier(parent) not in CHAT_TIERS:
                return

            session.add(
                ChatMessage(
                    child_id=child_id, sender_type="child", sender_id=None,
                    content=content, status="delivered",
                )
            )
            alerts = AlertService(session, self.fcm)
            await alerts.notify_family(
                child_id,
                "chat_reply",
                f"Message from {child.name}",
                content,
                {"device_id": str(device_id), "content": content},
            )
            await session.commit()
        logger.info("Inbound chat from child %s stored + family notified", child_id)
