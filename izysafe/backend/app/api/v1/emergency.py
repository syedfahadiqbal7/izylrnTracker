"""Emergency Contacts CRUD endpoints (Sprint 4 Slice 3, Premium).

Nested under a child like geofences; the SOS fan-out (Flow C) pushes urgent FCM to
any of these contacts who are also app users.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import success
from app.models.sos import EmergencyContact
from app.models.user import User
from app.schemas.emergency import (
    EmergencyContactCreate,
    EmergencyContactResponse,
    EmergencyContactUpdate,
)
from app.services.emergency_service import EmergencyContactService

router = APIRouter(tags=["emergency-contacts"])


def _serialize(contact: EmergencyContact) -> dict:
    return EmergencyContactResponse.model_validate(contact).model_dump(mode="json", by_alias=True)


@router.post("/children/{child_id}/emergency-contacts", status_code=201)
async def create_contact(
    child_id: uuid.UUID,
    payload: EmergencyContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add an emergency contact (manage permission + Premium tier)."""
    contact = await EmergencyContactService(db).create(
        current_user, child_id, payload.model_dump(exclude_unset=True)
    )
    return success(_serialize(contact))


@router.get("/children/{child_id}/emergency-contacts")
async def list_contacts(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await EmergencyContactService(db).list(current_user, child_id)
    return success([_serialize(c) for c in rows])


@router.put("/emergency-contacts/{contact_id}")
async def update_contact(
    contact_id: uuid.UUID,
    payload: EmergencyContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    contact = await EmergencyContactService(db).update(
        current_user, contact_id, payload.model_dump(exclude_unset=True)
    )
    return success(_serialize(contact))


@router.delete("/emergency-contacts/{contact_id}")
async def delete_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await EmergencyContactService(db).delete(current_user, contact_id)
    return success({"success": True})
