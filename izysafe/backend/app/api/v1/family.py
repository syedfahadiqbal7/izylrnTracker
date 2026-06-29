"""Family management endpoints (Sprint 1). This sub-slice: invite + accept."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_invite_gateway
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import success
from app.models.user import User
from app.schemas.family import AcceptResponse, InviteCreate, InviteResponse
from app.services.invite_gateway import InviteGateway
from app.services.invite_service import InviteService

router = APIRouter(tags=["family"])


@router.post("/children/{child_id}/family/invite", status_code=201)
async def invite_guardian(
    child_id: uuid.UUID,
    payload: InviteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    gateway: InviteGateway = Depends(get_invite_gateway),
) -> dict:
    """Invite a guardian by phone (requires manage permission on the child)."""
    invite, channel = await InviteService(db, gateway).create_invite(
        current_user, child_id, payload.model_dump()
    )
    body = InviteResponse(
        id=invite.id,
        child_id=invite.child_id,
        phone=invite.phone,
        role=invite.role,
        can_view=invite.can_view,
        can_call=invite.can_call,
        can_manage=invite.can_manage,
        expires_at=invite.expires_at,
        channel=channel,
        invite_link=f"{settings.invite_base_url}/{invite.token}",
    )
    return success(body.model_dump(mode="json"))


@router.post("/invites/{token}/accept")
async def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    gateway: InviteGateway = Depends(get_invite_gateway),
) -> dict:
    """Accept a guardian invite (the logged-in user's phone must match the invite)."""
    child, membership = await InviteService(db, gateway).accept_invite(current_user, token)
    body = AcceptResponse(
        child_id=child.id,
        child_name=child.name,
        role=membership.role,
        can_view=membership.can_view,
        can_call=membership.can_call,
        can_manage=membership.can_manage,
    )
    return success(body.model_dump(mode="json"))
