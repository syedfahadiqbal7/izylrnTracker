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

from sqlalchemy import func, or_, select
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
        """Enroll a student by the parent's phone. Model 1 (school-gated): the school
        PROVISIONS the parent + child — if either doesn't exist yet, they are created
        here (the parent later signs in by OTP to that account)."""
        phone = validate_phone(data["phone"])
        child = await self._resolve_or_create_child(phone, data.get("child_name"))

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
        if "location_opt_in" in fields and fields["location_opt_in"] is not None:
            enrollment.location_opt_in = fields["location_opt_in"]
            AuditService.log(
                self.db,
                action="enrollment.location_opt_in" if fields["location_opt_in"] else "enrollment.location_opt_out",
                actor_type="parent", actor_id=user.id, school_id=enrollment.school_id,
                entity_type="enrollment", entity_id=enrollment.id,
            )
        await self.db.commit()
        await self.db.refresh(enrollment)
        logger.info(
            "Enrollment %s consent updated (opt_in=%s bus=%s)",
            enrollment_id, enrollment.parent_opt_in, enrollment.bus_opt_in,
        )
        return enrollment

    # ------------------------------------------------- parents (Model 1 admin)
    async def list_parents(
        self, admin: SchoolAdmin, *, q: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Parents (primary guardians) of students enrolled at the admin's school,
        with the children they have AT THIS SCHOOL. Model 1 scoping: a school only
        sees parents of its own enrolled students."""
        base = (
            select(User.id, User.name, User.phone, User.last_login_at)
            .join(FamilyMember, FamilyMember.user_id == User.id)
            .join(Child, Child.id == FamilyMember.child_id)
            .join(StudentEnrollment, StudentEnrollment.child_id == Child.id)
            .where(
                StudentEnrollment.school_id == admin.school_id,
                FamilyMember.is_primary.is_(True),
                Child.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
            .distinct()
        )
        if q:
            like = f"%{q.strip().lower()}%"
            base = base.where(
                or_(func.lower(func.coalesce(User.name, "")).like(like), User.phone.like(like))
            )
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(User.name.nulls_last(), User.phone).limit(limit).offset(offset)
            )
        ).all()
        parents: list[dict[str, Any]] = [
            {"id": r.id, "name": r.name, "phone": r.phone,
             "last_login_at": r.last_login_at, "children": []}
            for r in rows
        ]
        if parents:
            by_id = {p["id"]: p for p in parents}
            crows = (
                await self.db.execute(
                    select(
                        User.id, Child.name, StudentEnrollment.class_grade,
                        StudentEnrollment.parent_opt_in, StudentEnrollment.location_opt_in,
                    )
                    .join(FamilyMember, FamilyMember.user_id == User.id)
                    .join(Child, Child.id == FamilyMember.child_id)
                    .join(StudentEnrollment, StudentEnrollment.child_id == Child.id)
                    .where(
                        StudentEnrollment.school_id == admin.school_id,
                        FamilyMember.is_primary.is_(True),
                        Child.deleted_at.is_(None),
                        User.id.in_(list(by_id.keys())),
                    )
                    .order_by(Child.name)
                )
            ).all()
            for cr in crows:
                by_id[cr.id]["children"].append({
                    "name": cr.name, "class_grade": cr.class_grade,
                    "parent_opt_in": cr.parent_opt_in, "location_opt_in": cr.location_opt_in,
                })
        return parents, total

    async def update_parent(
        self, admin: SchoolAdmin, user_id: uuid.UUID, name: str | None
    ) -> User:
        parent = await self._require_parent_at_school(admin, user_id)
        parent.name = (name or "").strip() or None
        AuditService.log(self.db, action="parent.update", actor_type="school_admin",
                         actor_id=admin.id, school_id=admin.school_id,
                         entity_type="user", entity_id=parent.id,
                         details={"name": parent.name})
        await self.db.commit()
        await self.db.refresh(parent)
        return parent

    async def remove_parent(self, admin: SchoolAdmin, user_id: uuid.UUID) -> None:
        """Remove a parent from this school: delete the school's enrollments for all
        their (primary) children. Model 1 — this revokes the parent's app access once
        they have no active enrollment anywhere. The account + history are retained."""
        await self._require_parent_at_school(admin, user_id)
        enrollments = (
            await self.db.execute(
                select(StudentEnrollment)
                .join(Child, Child.id == StudentEnrollment.child_id)
                .join(FamilyMember, FamilyMember.child_id == Child.id)
                .where(
                    StudentEnrollment.school_id == admin.school_id,
                    FamilyMember.user_id == user_id,
                    FamilyMember.is_primary.is_(True),
                )
            )
        ).scalars().all()
        for e in enrollments:
            await self.db.delete(e)
        AuditService.log(self.db, action="parent.remove", actor_type="school_admin",
                         actor_id=admin.id, school_id=admin.school_id,
                         entity_type="user", entity_id=user_id,
                         details={"removed_enrollments": len(enrollments)})
        await self.db.commit()

    async def _require_parent_at_school(self, admin: SchoolAdmin, user_id: uuid.UUID) -> User:
        parent = (
            await self.db.execute(
                select(User)
                .join(FamilyMember, FamilyMember.user_id == User.id)
                .join(Child, Child.id == FamilyMember.child_id)
                .join(StudentEnrollment, StudentEnrollment.child_id == Child.id)
                .where(
                    User.id == user_id,
                    StudentEnrollment.school_id == admin.school_id,
                    FamilyMember.is_primary.is_(True),
                    User.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if parent is None:
            raise APIException(404, "PARENT_NOT_FOUND", "No such parent at your school")
        return parent

    # ---------------------------------------------------------------- helpers
    async def _resolve_or_create_child(self, phone: str, child_name: str | None) -> Child:
        """Model 1 (school-gated) onboarding: find the parent + child, or CREATE them.

        - Parent not found → create a parent User for this phone (they'll sign in by OTP).
        - A matching primary-parent child exists → reuse it.
        - No matching child → create one (the school is provisioning this student); the
          student's name is then required.
        """
        parent = (
            await self.db.execute(
                select(User).where(User.phone == phone, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if parent is None:
            parent = User(
                phone=phone,
                country_code="+971" if phone.startswith("+971") else "+91",
            )
            self.db.add(parent)
            await self.db.flush()
            logger.info("Provisioned new parent account for %s (school-driven)", phone)

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

        if len(children) == 1:
            return children[0]
        if len(children) > 1:
            raise APIException(409, "AMBIGUOUS_CHILD", "Provide the student's name — this parent has multiple children")

        # No matching child → provision one. A name is required to create it.
        if not child_name or not child_name.strip():
            raise APIException(400, "CHILD_NAME_REQUIRED", "Enter the student's name to enroll them")
        child = Child(name=child_name.strip())
        self.db.add(child)
        await self.db.flush()
        self.db.add(
            FamilyMember(
                child_id=child.id, user_id=parent.id, role="parent",
                is_primary=True, can_view=True, can_call=True, can_manage=True,
            )
        )
        await self.db.flush()
        logger.info("Provisioned child %s for parent %s (school-driven)", child.id, phone)
        return child

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
