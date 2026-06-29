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
from app.schemas.family import (
    AcceptResponse,
    FamilyMemberResponse,
    InviteCreate,
    InviteResponse,
    MemberUpdate,
    PendingInviteResponse,
)
from app.services.family_service import FamilyService
from app.services.invite_gateway import InviteGateway
from app.services.invite_service import InviteService

router = APIRouter(tags=["family"])


def _member_body(fm, member_user) -> dict:
    return FamilyMemberResponse(
        id=fm.id,
        user_id=fm.user_id,
        name=member_user.name,
        phone=member_user.phone,
        role=fm.role,
        is_primary=fm.is_primary,
        can_view=fm.can_view,
        can_call=fm.can_call,
        can_manage=fm.can_manage,
        joined_at=fm.created_at,
    ).model_dump(mode="json")


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


@router.get("/children/{child_id}/family")
async def list_family(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all family members of a child (requires view permission)."""
    rows = await FamilyService(db).list_members(current_user, child_id)
    return success([_member_body(fm, u) for fm, u in rows])


@router.put("/children/{child_id}/family/{member_id}")
async def update_member(
    child_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: MemberUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update a member's role/permissions (requires manage; primary protected)."""
    fm, member_user = await FamilyService(db).update_member(
        current_user, child_id, member_id, payload.model_dump(exclude_unset=True)
    )
    return success(_member_body(fm, member_user))


@router.delete("/children/{child_id}/family/{member_id}")
async def remove_member(
    child_id: uuid.UUID,
    member_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove a member. Self-removal is allowed; removing others needs manage."""
    await FamilyService(db).remove_member(current_user, child_id, member_id)
    return success({"success": True})


@router.get("/children/{child_id}/invites")
async def list_pending_invites(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List pending (un-accepted) invites for a child (requires manage)."""
    service = FamilyService(db)
    invites = await service.list_invites(current_user, child_id)
    return success(
        [
            PendingInviteResponse(
                id=i.id, phone=i.phone, role=i.role,
                can_view=i.can_view, can_call=i.can_call, can_manage=i.can_manage,
                expires_at=i.expires_at, created_at=i.created_at,
                expired=FamilyService.is_expired(i),
            ).model_dump(mode="json")
            for i in invites
        ]
    )


@router.delete("/invites/{token}")
async def revoke_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke a pending invite (requires manage on the invite's child)."""
    await FamilyService(db).revoke_invite(current_user, token)
    return success({"success": True})
