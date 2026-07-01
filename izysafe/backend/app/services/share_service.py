"""Share Links + live-location reads (Sprint 7 Slice 3, F22).

Two surfaces onto a child's live position:
  * Share Links — public, login-less tracking URLs. Creation/list/revoke are
    authed and Basic+ (CLAUDE.md §10), authorized through `family_members` like
    every other child resource. `GET /share/{token}` is PUBLIC (the token is the
    credential): it's IP-rate-limited, refuses revoked/expired links with a generic
    404, bumps `view_count`, and returns only the child's first name + latest fix
    (Decision D10 — never history/battery/device).
  * Latest location — an authed `GET /children/{id}/location/latest` reading the
    same Redis `location:child:{id}:latest` cache (Decision D12).

Both read the shared latest-fix cache via `_latest_payload`, so the public and
authed views stay consistent.
"""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.errors import APIException
from app.models.child import Child, FamilyMember
from app.models.route import ShareLink
from app.models.user import User
from app.services.children_service import ChildrenService, effective_tier

# Share Link is a Basic+ feature (School inherits it).
SHARE_TIERS = {"basic", "premium", "school"}

logger = logging.getLogger("izysafe.share")


class ShareService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis
        self.children = ChildrenService(db)

    # ----------------------------------------------------------------- create
    async def create_link(self, user, child_id: uuid.UUID, ttl_hours: int) -> ShareLink:
        await self.children.get_child(user, child_id, require="manage")
        self._enforce_tier(await self._child_tier(child_id))

        link = ShareLink(
            child_id=child_id,
            token=secrets.token_hex(32),  # 64 hex chars — fits token VARCHAR(64)
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
            created_by=user.id,
        )
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)
        return link

    # ------------------------------------------------------------------- read
    async def list_links(self, user, child_id: uuid.UUID) -> list[ShareLink]:
        await self.children.get_child(user, child_id, require="view")
        rows = (
            await self.db.execute(
                select(ShareLink)
                .where(ShareLink.child_id == child_id)
                .order_by(ShareLink.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def latest_location(self, user, child_id: uuid.UUID) -> dict | None:
        """Authed live-location read for a child (Decision D12)."""
        await self.children.get_child(user, child_id, require="view")
        return await self._latest_payload(child_id)

    # ----------------------------------------------------------------- revoke
    async def revoke_link(self, user, link_id: uuid.UUID) -> None:
        link, _ = await self._require_link(user.id, link_id, "manage")
        link.revoked = True  # soft revoke — keep the row (view_count/audit)
        await self.db.commit()

    # ------------------------------------------------------------- public read
    async def resolve_public(self, token: str, ip: str | None) -> dict:
        """Resolve a public share token → {child_name, location, expires_at}. Rate-
        limited per IP; revoked/expired/unknown tokens all get a generic 404."""
        await self._rate_limit(ip)

        link = (
            await self.db.execute(select(ShareLink).where(ShareLink.token == token))
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if link is None or link.revoked or link.expires_at <= now:
            raise APIException(404, "SHARE_LINK_NOT_FOUND", "This tracking link is invalid or has expired")

        child = (
            await self.db.execute(
                select(Child).where(Child.id == link.child_id, Child.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if child is None:
            raise APIException(404, "SHARE_LINK_NOT_FOUND", "This tracking link is invalid or has expired")

        await self.db.execute(
            update(ShareLink)
            .where(ShareLink.id == link.id)
            .values(view_count=ShareLink.view_count + 1)
        )
        await self.db.commit()

        return {
            "child_name": child.name.split(" ")[0],  # first name only (D10)
            "location": await self._latest_payload(link.child_id),
            "expires_at": link.expires_at,
        }

    # ---------------------------------------------------------------- helpers
    async def _latest_payload(self, child_id: uuid.UUID) -> dict | None:
        """Latest fix for a child from Redis, trimmed to {lat, lng, timestamp} (D10)."""
        cached = await self.redis.get(rk.loc_child_latest(child_id))
        if cached is None:
            return None
        data: dict[str, Any] = json.loads(cached)
        if data.get("lat") is None or data.get("lng") is None:
            return None
        return {"lat": data["lat"], "lng": data["lng"], "timestamp": data.get("ts")}

    async def _rate_limit(self, ip: str | None) -> None:
        if not ip:
            return
        key = rk.share_view_rate(ip)
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 60)
        if count > settings.share_view_rate_per_min:
            raise APIException(429, "RATE_LIMIT_SHARE", "Too many requests — please wait a moment")

    def _enforce_tier(self, tier: str) -> None:
        if tier not in SHARE_TIERS:
            raise APIException(
                402, "SHARE_LINK_REQUIRES_BASIC",
                "Upgrade to Basic plan to share live-tracking links",
            )

    async def _child_tier(self, child_id: uuid.UUID) -> str:
        primary = (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .where(FamilyMember.child_id == child_id, FamilyMember.is_primary.is_(True))
            )
        ).scalars().first()
        return effective_tier(primary) if primary else "free"

    async def _require_link(
        self, user_id: uuid.UUID, link_id: uuid.UUID, need: str
    ) -> tuple[ShareLink, FamilyMember]:
        row = (
            await self.db.execute(
                select(ShareLink, FamilyMember)
                .join(FamilyMember, FamilyMember.child_id == ShareLink.child_id)
                .where(ShareLink.id == link_id, FamilyMember.user_id == user_id)
            )
        ).first()
        # 404 (not 403) when the user has no membership — don't reveal existence.
        if row is None:
            raise APIException(404, "SHARE_LINK_NOT_FOUND", "Share link not found")
        link, membership = row
        if need == "manage" and not membership.can_manage:
            raise APIException(403, "FORBIDDEN", "You don't have permission to manage this link")
        return link, membership
