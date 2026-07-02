"""Parent-side enrollment endpoints (Sprint 8 Slice 2, F26 consent).

The consumer app surfaces a parent's school enrollment requests here and lets them
grant/withdraw consent (Decision B/D5). Parent JWT (`get_current_user`); consent
changes require manage permission on the child (enforced in the service).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import success
from app.models.child import Child
from app.models.school import School, StudentEnrollment
from app.models.user import User
from app.schemas.school import EnrollmentConsentRequest, ParentEnrollmentResponse
from app.services.enrollment_service import EnrollmentService

router = APIRouter(prefix="/enrollments", tags=["enrollments"])


def _serialize(e: StudentEnrollment, school: School, child: Child) -> dict:
    return ParentEnrollmentResponse(
        id=e.id, school_id=e.school_id, school_name=school.name,
        child_id=e.child_id, child_name=child.name, class_grade=e.class_grade,
        parent_opt_in=e.parent_opt_in, bus_opt_in=e.bus_opt_in, enrolled_at=e.enrolled_at,
    ).model_dump(mode="json")


@router.get("")
async def list_my_enrollments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enrollment requests + active consents across the caller's children."""
    rows = await EnrollmentService(db).list_for_parent(current_user)
    return success([_serialize(e, s, c) for e, s, c in rows])


@router.put("/{enrollment_id}")
async def update_consent(
    enrollment_id: uuid.UUID,
    payload: EnrollmentConsentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Grant/withdraw school visibility (parent_opt_in) and bus consent (bus_opt_in).
    Requires manage permission on the child."""
    enrollment = await EnrollmentService(db).update_consent(
        current_user, enrollment_id, payload.model_dump(exclude_unset=True)
    )
    # Re-load school + child for the response shape.
    school = (await db.execute(select(School).where(School.id == enrollment.school_id))).scalar_one()
    child = (await db.execute(select(Child).where(Child.id == enrollment.child_id))).scalar_one()
    return success(_serialize(enrollment, school, child))
