"""Children CRUD endpoints (Sprint 1)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import success
from app.models.child import Child, FamilyMember
from app.models.user import User
from app.schemas.child import ChildCreate, ChildPermissions, ChildResponse, ChildUpdate
from app.services.children_service import ChildrenService

router = APIRouter(prefix="/children", tags=["children"])


def _serialize(child: Child, membership: FamilyMember, device_count: int) -> dict:
    resp = ChildResponse.model_validate(child)
    resp.device_count = device_count
    resp.permissions = ChildPermissions(
        role=membership.role,
        is_primary=membership.is_primary,
        can_view=membership.can_view,
        can_call=membership.can_call,
        can_manage=membership.can_manage,
    )
    return resp.model_dump(mode="json")


@router.post("", status_code=201)
async def create_child(
    payload: ChildCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a child; the creator becomes the primary parent (full permissions)."""
    child, membership = await ChildrenService(db).create_child(
        current_user, payload.model_dump(exclude_unset=True)
    )
    return success(_serialize(child, membership, device_count=0))


@router.get("")
async def list_children(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all children the user can see, with device counts."""
    rows = await ChildrenService(db).list_children(current_user)
    return success([_serialize(c, fm, n) for c, fm, n in rows])


@router.get("/{child_id}")
async def get_child(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    child, membership, device_count = await ChildrenService(db).get_child(
        current_user, child_id, require="view"
    )
    return success(_serialize(child, membership, device_count))


@router.put("/{child_id}")
async def update_child(
    child_id: uuid.UUID,
    payload: ChildUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update child info/settings (requires manage permission)."""
    child, membership = await ChildrenService(db).update_child(
        current_user, child_id, payload.model_dump(exclude_unset=True)
    )
    _, _, device_count = await ChildrenService(db).get_child(current_user, child_id, "view")
    return success(_serialize(child, membership, device_count))


@router.delete("/{child_id}")
async def delete_child(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete a child (primary parent only); data retained 30 days."""
    await ChildrenService(db).soft_delete_child(current_user, child_id)
    return success({"success": True})
