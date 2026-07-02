"""Enrollment + parent opt-in (Sprint 8 Slice 2) — the privacy/authorization backbone.

Decision B: a school sees a child's data ONLY after the parent consents. The flow is
school-initiated (Decision D3): an admin enrolls a student **by the parent's phone**
(the school resolves the exact child by name), creating a `student_enrollments` row
with `parent_opt_in=FALSE`. The child's family member (manage permission) then
approves in the app, flipping `parent_opt_in` — and can withdraw anytime (Decision D5),
after which school access stops but historical records are retained. `bus_opt_in` is a
separate consent.

`require_enrolled_child` is the gate every later school slice uses: it returns the
enrollment only when it belongs to the admin's school AND `parent_opt_in` is TRUE,
otherwise 404 (never reveal a child the school may not see) — mirroring the
`family_members` 404 rule.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIException
from app.core.validators import validate_phone
from app.models.child import Child, FamilyMember
from app.models.school import School, SchoolAdmin, StudentEnrollment
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.children_service import ChildrenService

logger = logging.getLogger("izysafe.enrollment")


class EnrollmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.children = ChildrenService(db)

    # ------------------------------------------------------------ school side
    async def enroll(self, admin: SchoolAdmin, data: dict[str, Any]) -> tuple[StudentEnrollment, Child]:
        """Enroll a student by the parent's phone (school resolves the exact child)."""
        phone = validate_phone(data["phone"])
        child = await self._resolve_child(phone, data.get("child_name"))

        existing = (
            await self.db.execute(
                select(StudentEnrollment).where(
                    StudentEnrollment.school_id == admin.school_id,
                    StudentEnrollment.child_id == child.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise APIException(409, "ALREADY_ENROLLED", "This student is already enrolled")

        enrollment = StudentEnrollment(
            school_id=admin.school_id, child_id=child.id,
            class_grade=data.get("class_grade"), parent_opt_in=False, bus_opt_in=False,
        )
        self.db.add(enrollment)
        await self.db.flush()
        AuditService.log(self.db, action="enrollment.create", actor_type="school_admin",
                         actor_id=admin.id, school_id=admin.school_id,
                         entity_type="enrollment", entity_id=enrollment.id,
                         details={"child_id": str(child.id), "class_grade": enrollment.class_grade})
        await self.db.commit()
        await self.db.refresh(enrollment)
        logger.info("School %s enrolled child %s (pending consent)", admin.school_id, child.id)
        return enrollment, child

    async def list_roster(
        self, admin: SchoolAdmin, *, class_grade: str | None, opted_in: bool | None,
        q: str | None, limit: int, offset: int,
    ) -> tuple[list[tuple[StudentEnrollment, Child, str | None, str | None]], int]:
        conditions = [StudentEnrollment.school_id == admin.school_id]
        if class_grade is not None:
            conditions.append(StudentEnrollment.class_grade == class_grade)
        if opted_in is not None:
            conditions.append(StudentEnrollment.parent_opt_in.is_(opted_in))
        if q:
            conditions.append(Child.name.ilike(f"%{q.strip()}%"))

        base = (
            select(StudentEnrollment, Child)
            .join(Child, Child.id == StudentEnrollment.child_id)
            .where(*conditions)
        )
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(StudentEnrollment.enrolled_at.desc()).limit(limit).offset(offset)
            )
        ).all()

        # Resolve each child's primary parent (name + phone) in one extra query,
        # avoiding row multiplication from the two-primary-parents case.
        child_ids = [c.id for _, c in rows]
        parents: dict[uuid.UUID, tuple[str | None, str | None]] = {}
        if child_ids:
            for cid, name, phone in (
                await self.db.execute(
                    select(FamilyMember.child_id, User.name, User.phone)
                    .join(User, User.id == FamilyMember.user_id)
                    .where(
                        FamilyMember.child_id.in_(child_ids),
                        FamilyMember.is_primary.is_(True),
                        User.deleted_at.is_(None),
                    )
                )
            ).all():
                parents.setdefault(cid, (name, phone))
        return [(e, c, *parents.get(c.id, (None, None))) for e, c in rows], total

    async def update(
        self, admin: SchoolAdmin, enrollment_id: uuid.UUID, fields: dict[str, Any]
    ) -> tuple[StudentEnrollment, Child]:
        """Update the school-owned enrollment fields (class/grade)."""
        enrollment = await self._require_own(admin, enrollment_id)
        if "class_grade" in fields:
            enrollment.class_grade = fields["class_grade"]
        AuditService.log(self.db, action="enrollment.update", actor_type="school_admin",
                         actor_id=admin.id, school_id=admin.school_id,
                         entity_type="enrollment", entity_id=enrollment.id,
                         details={"class_grade": enrollment.class_grade})
        await self.db.commit()
        await self.db.refresh(enrollment)
        child = (
            await self.db.execute(select(Child).where(Child.id == enrollment.child_id))
        ).scalar_one()
        return enrollment, child

    async def remove(self, admin: SchoolAdmin, enrollment_id: uuid.UUID) -> None:
        enrollment = await self._require_own(admin, enrollment_id)
        AuditService.log(self.db, action="enrollment.remove", actor_type="school_admin",
                         actor_id=admin.id, school_id=admin.school_id,
                         entity_type="enrollment", entity_id=enrollment.id,
                         details={"child_id": str(enrollment.child_id)})
        await self.db.delete(enrollment)
        await self.db.commit()

    async def require_enrolled_child(
        self, admin: SchoolAdmin, child_id: uuid.UUID
    ) -> StudentEnrollment:
        """THE authorization backbone (Decision B/D4). Later slices call this before
        exposing any child data. 404 when not enrolled+consented for this school."""
        enrollment = (
            await self.db.execute(
                select(StudentEnrollment).where(
                    StudentEnrollment.school_id == admin.school_id,
                    StudentEnrollment.child_id == child_id,
                    StudentEnrollment.parent_opt_in.is_(True),
                )
            )
        ).scalar_one_or_none()
        if enrollment is None:
            raise APIException(404, "CHILD_NOT_ENROLLED", "Student not found")
        return enrollment

    # ------------------------------------------------------------ parent side
    async def list_for_parent(self, user) -> list[tuple[StudentEnrollment, School, Child]]:
        rows = (
            await self.db.execute(
                select(StudentEnrollment, School, Child)
                .join(Child, Child.id == StudentEnrollment.child_id)
                .join(School, School.id == StudentEnrollment.school_id)
                .join(FamilyMember, FamilyMember.child_id == Child.id)
                .where(FamilyMember.user_id == user.id, Child.deleted_at.is_(None))
                .order_by(StudentEnrollment.enrolled_at.desc())
            )
        ).all()
        return [(e, s, c) for e, s, c in rows]

    async def update_consent(
        self, user, enrollment_id: uuid.UUID, fields: dict[str, Any]
    ) -> StudentEnrollment:
        """Parent approves/withdraws consent. Requires manage permission on the child;
        404 for non-managers/unknown enrollment (don't reveal existence)."""
        enrollment = (
            await self.db.execute(
                select(StudentEnrollment).where(StudentEnrollment.id == enrollment_id)
            )
        ).scalar_one_or_none()
        if enrollment is None:
            raise APIException(404, "ENROLLMENT_NOT_FOUND", "Enrollment not found")
        # Authorize via the owning child (manage) — raises 404 for non-members.
        await self.children.get_child(user, enrollment.child_id, require="manage")

        if "parent_opt_in" in fields and fields["parent_opt_in"] is not None:
            enrollment.parent_opt_in = fields["parent_opt_in"]
            AuditService.log(
                self.db,
                action="enrollment.opt_in" if fields["parent_opt_in"] else "enrollment.opt_out",
                actor_type="parent", actor_id=user.id, school_id=enrollment.school_id,
                entity_type="enrollment", entity_id=enrollment.id,
            )
        if "bus_opt_in" in fields and fields["bus_opt_in"] is not None:
            enrollment.bus_opt_in = fields["bus_opt_in"]
        await self.db.commit()
        await self.db.refresh(enrollment)
        logger.info(
            "Enrollment %s consent updated (opt_in=%s bus=%s)",
            enrollment_id, enrollment.parent_opt_in, enrollment.bus_opt_in,
        )
        return enrollment

    # ---------------------------------------------------------------- helpers
    async def _resolve_child(self, phone: str, child_name: str | None) -> Child:
        parent = (
            await self.db.execute(
                select(User).where(User.phone == phone, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if parent is None:
            raise APIException(
                404, "PARENT_NOT_FOUND", "No parent account for this number — ask them to install the app first"
            )
        stmt = (
            select(Child)
            .join(FamilyMember, FamilyMember.child_id == Child.id)
            .where(
                FamilyMember.user_id == parent.id,
                FamilyMember.is_primary.is_(True),
                Child.deleted_at.is_(None),
            )
        )
        if child_name:
            stmt = stmt.where(func.lower(Child.name) == child_name.strip().lower())
        children = (await self.db.execute(stmt)).scalars().all()

        if not children:
            raise APIException(404, "CHILD_NOT_FOUND", "No matching student for this parent")
        if len(children) > 1:
            raise APIException(409, "AMBIGUOUS_CHILD", "Provide the student's name — this parent has multiple children")
        return children[0]

    async def _require_own(self, admin: SchoolAdmin, enrollment_id: uuid.UUID) -> StudentEnrollment:
        enrollment = (
            await self.db.execute(
                select(StudentEnrollment).where(
                    StudentEnrollment.id == enrollment_id,
                    StudentEnrollment.school_id == admin.school_id,
                )
            )
        ).scalar_one_or_none()
        if enrollment is None:
            raise APIException(404, "ENROLLMENT_NOT_FOUND", "Enrollment not found")
        return enrollment
