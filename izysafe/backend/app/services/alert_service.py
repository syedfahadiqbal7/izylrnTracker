"""Shared alert fan-out: notification inbox rows + FCM push to a child's family.

Every alert (device offline this slice; battery/speed/geofence later) goes through
`notify_family`: it inserts one `alerts` row per family member (CLAUDE.md — every
push also lands in the inbox) and pushes to those members' FCM tokens.

The caller owns the transaction — `notify_family` adds rows to the passed session
but does NOT commit, so a caller can batch several DB changes (e.g. flip
`is_online` AND write the alert) into one atomic commit.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIException
from app.models.alert import Alert
from app.models.child import FamilyMember
from app.models.user import User
from app.services.fcm_gateway import FcmGateway


class AlertService:
    def __init__(self, db: AsyncSession, fcm: FcmGateway) -> None:
        self.db = db
        self.fcm = fcm

    async def notify_family(
        self,
        child_id: uuid.UUID,
        alert_type: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        urgent: bool = False,
    ) -> int:
        """Insert inbox rows for every family member and push to their devices.
        Returns the number of FCM tokens targeted (for logging/tests). urgent=True
        sends a MAX-priority push that bypasses DND (SOS — Flow C)."""
        members = (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .where(FamilyMember.child_id == child_id, User.deleted_at.is_(None))
            )
        ).scalars().all()

        tokens: list[str] = []
        for user in members:
            self.db.add(
                Alert(
                    user_id=user.id,
                    child_id=child_id,
                    type=alert_type,
                    title=title,
                    body=body,
                    data=data,
                )
            )
            if user.fcm_token:
                tokens.append(user.fcm_token)

        await self.fcm.send(
            tokens, title, body, {**(data or {}), "type": alert_type}, urgent=urgent
        )
        return len(tokens)

    async def notify_user(
        self,
        user_id: uuid.UUID,
        alert_type: str,
        title: str,
        body: str,
        child_id: uuid.UUID | None = None,
        data: dict[str, Any] | None = None,
    ) -> int:
        """Notify a single user (e.g. 'guardian accepted your invite'). Inserts one
        inbox row and pushes to that user's token. Caller owns the transaction."""
        user = await self.db.get(User, user_id)
        if user is None or user.deleted_at is not None:
            return 0
        self.db.add(
            Alert(
                user_id=user_id,
                child_id=child_id,
                type=alert_type,
                title=title,
                body=body,
                data=data,
            )
        )
        tokens = [user.fcm_token] if user.fcm_token else []
        await self.fcm.send(tokens, title, body, {**(data or {}), "type": alert_type})
        return len(tokens)


class AlertInboxService:
    """Request-path read side of the notification inbox (Sprint 4 Slice 4).

    The inbox is per-user: every query is scoped to ``Alert.user_id == user.id``, so
    a user only ever sees / mutates their own rows (a foreign alert id → 404)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        user,
        *,
        unread: bool = False,
        child_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Alert], int, int]:
        """Return (rows, total, unread_count) for the user's inbox, newest first.
        `total` honors the unread/child filters; `unread_count` honors only child."""
        filters = [Alert.user_id == user.id]
        if child_id is not None:
            filters.append(Alert.child_id == child_id)
        scoped = list(filters)
        if unread:
            scoped.append(Alert.read.is_(False))

        total = (
            await self.db.execute(select(func.count()).select_from(Alert).where(*scoped))
        ).scalar_one()
        unread_count = (
            await self.db.execute(
                select(func.count()).select_from(Alert).where(*filters, Alert.read.is_(False))
            )
        ).scalar_one()
        rows = (
            await self.db.execute(
                select(Alert)
                .where(*scoped)
                .order_by(Alert.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).scalars().all()
        return list(rows), total, unread_count

    async def mark_read(self, user, alert_id: uuid.UUID) -> Alert:
        alert = (
            await self.db.execute(
                select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id)
            )
        ).scalar_one_or_none()
        if alert is None:
            raise APIException(404, "ALERT_NOT_FOUND", "Alert not found")
        alert.read = True  # idempotent
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def mark_all_read(self, user, child_id: uuid.UUID | None = None) -> int:
        """Mark every unread alert read (optionally scoped to one child). Returns the
        number flipped."""
        filters = [Alert.user_id == user.id, Alert.read.is_(False)]
        if child_id is not None:
            filters.append(Alert.child_id == child_id)
        result = await self.db.execute(update(Alert).where(*filters).values(read=True))
        await self.db.commit()
        return result.rowcount
