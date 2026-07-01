"""Share Link + live-location endpoints (Sprint 7 Slice 3, F22).

Owner endpoints nest under a child (`/children/{id}/share-links`) or address a link
directly (`/share-links/{id}`) and require auth + Basic+. The PUBLIC tracking read
(`GET /share/{token}`) carries NO auth — the unguessable token is the credential
(CLAUDE.md §7 lists /webhook/* as the only other JWT-exempt path; this is a
deliberate third exception) — and is IP-rate-limited in the service.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import success
from app.core.redis import get_redis
from app.models.route import ShareLink
from app.models.user import User
from app.schemas.share import (
    LatestLocation,
    PublicShareResponse,
    ShareLinkCreate,
    ShareLinkResponse,
)
from app.services.share_service import ShareService

router = APIRouter(tags=["share"])


def _serialize(link: ShareLink) -> dict:
    return ShareLinkResponse(
        id=link.id,
        child_id=link.child_id,
        token=link.token,
        url=f"{settings.share_link_base_url}/{link.token}",
        expires_at=link.expires_at,
        view_count=link.view_count,
        revoked=link.revoked,
        created_at=link.created_at,
    ).model_dump(mode="json")


@router.post("/children/{child_id}/share-links", status_code=201)
async def create_share_link(
    child_id: uuid.UUID,
    payload: ShareLinkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Create a public tracking link for a child (requires manage permission + Basic+)."""
    link = await ShareService(db, redis).create_link(current_user, child_id, payload.ttl_hours)
    return success(_serialize(link))


@router.get("/children/{child_id}/share-links")
async def list_share_links(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """List a child's tracking links (most recent first)."""
    rows = await ShareService(db, redis).list_links(current_user, child_id)
    return success([_serialize(link) for link in rows])


@router.delete("/share-links/{link_id}")
async def revoke_share_link(
    link_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Revoke a tracking link (requires manage permission)."""
    await ShareService(db, redis).revoke_link(current_user, link_id)
    return success({"success": True})


@router.get("/children/{child_id}/location/latest")
async def latest_location(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Latest known live location for a child (requires view permission)."""
    payload = await ShareService(db, redis).latest_location(current_user, child_id)
    location = LatestLocation(**payload).model_dump(mode="json") if payload else None
    return success({"location": location})


@router.get("/share/{token}")
async def public_share(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """PUBLIC — resolve a share token to a child's name + live location. No auth; the
    token is the credential. IP-rate-limited; revoked/expired links return 404."""
    client_ip = request.client.host if request.client else None
    data = await ShareService(db, redis).resolve_public(token, client_ip)
    return success(PublicShareResponse(**data).model_dump(mode="json"))
