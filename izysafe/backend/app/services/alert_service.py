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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    ) -> int:
        """Insert inbox rows for every family member and push to their devices.
        Returns the number of FCM tokens targeted (for logging/tests)."""
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

        await self.fcm.send(tokens, title, body, {**(data or {}), "type": alert_type})
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
