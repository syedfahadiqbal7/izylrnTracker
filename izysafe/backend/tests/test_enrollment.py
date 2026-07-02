"""Tests for Enrollment + parent opt-in (Sprint 8 Slice 2) — the privacy backbone.

Covers school-side enroll-by-phone (child resolution, ambiguity, dup, unknown parent),
roster listing + filters + tenant isolation, removal; parent-side consent
(approve/withdraw/bus, manage-permission + 404 rules); and the `require_enrolled_child`
authorization gate later slices depend on.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.errors import APIException
from app.core.security import create_access_token, hash_secret
from app.models.child import Child, FamilyMember
from app.models.school import School, SchoolAdmin, StudentEnrollment
from app.models.user import User
from app.services.enrollment_service import EnrollmentService

STUDENTS = "/api/v1/schools/students"
ENROLLMENTS = "/api/v1/enrollments"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _school_admin(db, *, name="Green Valley", role="admin"):
    school = School(name=name, timezone="Asia/Kolkata")
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(
        school_id=school.id, email=f"a-{uuid.uuid4().hex[:8]}@s.test",
        password_hash=hash_secret("password123"), role=role, active=True,
    )
    db.add(admin)
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(admin.id), extra={'scope': 'school_admin'})}"}
    return school, admin, hdr


async def _parent_with_children(db, *, phone=None, names=("Aryan",), can_manage=True):
    phone = phone or "+9198" + uuid.uuid4().hex[:8]
    parent = User(phone=phone, country_code="+91")
    db.add(parent)
    await db.flush()
    children = []
    for nm in names:
        child = Child(name=nm)
        db.add(child)
        await db.flush()
        db.add(FamilyMember(
            child_id=child.id, user_id=parent.id, role="parent",
            is_primary=True, can_view=True, can_call=True, can_manage=can_manage,
        ))
        children.append(child)
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(parent.id))}"}
    return parent, children, hdr


# --------------------------------------------------------------------------- #
# School-side enroll
# --------------------------------------------------------------------------- #
async def test_enroll_single_child(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    parent, (child,), _ = await _parent_with_children(db_session, phone="+919812345678")
    resp = await client.post(STUDENTS, headers=admin_hdr,
                             json={"phone": "+919812345678", "class_grade": "5A"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["child_id"] == str(child.id)
    assert data["child_name"] == "Aryan"
    assert data["parent_opt_in"] is False  # pending consent
    assert data["class_grade"] == "5A"


async def test_enroll_ambiguous_needs_name(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    await _parent_with_children(db_session, phone="+919811111111", names=("Aryan", "Diya"))
    resp = await client.post(STUDENTS, headers=admin_hdr, json={"phone": "+919811111111"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "AMBIGUOUS_CHILD"


async def test_enroll_with_name_disambiguates(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    _, children, _ = await _parent_with_children(db_session, phone="+919822222222", names=("Aryan", "Diya"))
    resp = await client.post(STUDENTS, headers=admin_hdr,
                             json={"phone": "+919822222222", "child_name": "Diya"})
    assert resp.status_code == 201
    assert resp.json()["data"]["child_id"] == str(children[1].id)


async def test_enroll_parent_not_found(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    resp = await client.post(STUDENTS, headers=admin_hdr, json={"phone": "+919800000000"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "PARENT_NOT_FOUND"


async def test_enroll_child_name_no_match(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    await _parent_with_children(db_session, phone="+919833333333", names=("Aryan",))
    resp = await client.post(STUDENTS, headers=admin_hdr,
                             json={"phone": "+919833333333", "child_name": "Nobody"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_FOUND"


async def test_enroll_duplicate(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    await _parent_with_children(db_session, phone="+919844444444")
    body = {"phone": "+919844444444"}
    assert (await client.post(STUDENTS, headers=admin_hdr, json=body)).status_code == 201
    resp = await client.post(STUDENTS, headers=admin_hdr, json=body)
    assert resp.status_code == 409
    assert resp.json()["code"] == "ALREADY_ENROLLED"


async def test_enroll_invalid_phone(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    resp = await client.post(STUDENTS, headers=admin_hdr, json={"phone": "12345"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PHONE"


async def test_enroll_requires_admin_auth(client, db_session, auth_headers):
    resp = await client.post(STUDENTS, headers=auth_headers, json={"phone": "+919812345678"})
    assert resp.status_code == 401  # parent token has no school_admin scope


# --------------------------------------------------------------------------- #
# Roster
# --------------------------------------------------------------------------- #
async def _enroll(client, admin_hdr, phone, **extra):
    return await client.post(STUDENTS, headers=admin_hdr, json={"phone": phone, **extra})


async def test_roster_lists_and_counts(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    await _parent_with_children(db_session, phone="+919851111111")
    await _parent_with_children(db_session, phone="+919852222222")
    await _enroll(client, admin_hdr, "+919851111111", class_grade="5A")
    await _enroll(client, admin_hdr, "+919852222222", class_grade="6B")

    resp = await client.get(STUDENTS, headers=admin_hdr)
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 2


async def test_roster_filter_class_grade(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    await _parent_with_children(db_session, phone="+919853333333")
    await _parent_with_children(db_session, phone="+919854444444")
    await _enroll(client, admin_hdr, "+919853333333", class_grade="5A")
    await _enroll(client, admin_hdr, "+919854444444", class_grade="6B")

    resp = await client.get(f"{STUDENTS}?class_grade=5A", headers=admin_hdr)
    assert len(resp.json()["data"]) == 1
    assert resp.json()["data"][0]["class_grade"] == "5A"


async def test_roster_filter_opted_in(client, db_session):
    school, _, admin_hdr = await _school_admin(db_session)
    _, (child,), _ = await _parent_with_children(db_session, phone="+919855555555")
    await _enroll(client, admin_hdr, "+919855555555")
    # flip opt-in directly
    enr = (await db_session.execute(select(StudentEnrollment).where(StudentEnrollment.child_id == child.id))).scalar_one()
    enr.parent_opt_in = True
    await db_session.flush()

    assert len((await client.get(f"{STUDENTS}?opted_in=true", headers=admin_hdr)).json()["data"]) == 1
    assert len((await client.get(f"{STUDENTS}?opted_in=false", headers=admin_hdr)).json()["data"]) == 0


async def test_roster_tenant_isolation(client, db_session):
    _, _, hdr_a = await _school_admin(db_session, name="School A")
    _, _, hdr_b = await _school_admin(db_session, name="School B")
    await _parent_with_children(db_session, phone="+919856666666")
    await _enroll(client, hdr_a, "+919856666666")

    assert (await client.get(STUDENTS, headers=hdr_a)).json()["meta"]["total"] == 1
    assert (await client.get(STUDENTS, headers=hdr_b)).json()["meta"]["total"] == 0


async def test_remove_enrollment(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    await _parent_with_children(db_session, phone="+919857777777")
    eid = (await _enroll(client, admin_hdr, "+919857777777")).json()["data"]["id"]
    assert (await client.delete(f"{STUDENTS}/{eid}", headers=admin_hdr)).status_code == 200
    assert (await client.get(STUDENTS, headers=admin_hdr)).json()["meta"]["total"] == 0


async def test_remove_other_school_404(client, db_session):
    _, _, hdr_a = await _school_admin(db_session, name="A")
    _, _, hdr_b = await _school_admin(db_session, name="B")
    await _parent_with_children(db_session, phone="+919858888888")
    eid = (await _enroll(client, hdr_a, "+919858888888")).json()["data"]["id"]
    assert (await client.delete(f"{STUDENTS}/{eid}", headers=hdr_b)).status_code == 404


# --------------------------------------------------------------------------- #
# Parent-side consent
# --------------------------------------------------------------------------- #
async def test_parent_lists_enrollments(client, db_session):
    school, _, admin_hdr = await _school_admin(db_session, name="Sunrise School")
    _, _, parent_hdr = await _parent_with_children(db_session, phone="+919861111111")
    await _enroll(client, admin_hdr, "+919861111111")

    resp = await client.get(ENROLLMENTS, headers=parent_hdr)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["school_name"] == "Sunrise School"
    assert data[0]["parent_opt_in"] is False


async def test_parent_approves_and_withdraws(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    _, _, parent_hdr = await _parent_with_children(db_session, phone="+919862222222")
    await _enroll(client, admin_hdr, "+919862222222")
    eid = (await client.get(ENROLLMENTS, headers=parent_hdr)).json()["data"][0]["id"]

    approve = await client.put(f"{ENROLLMENTS}/{eid}", headers=parent_hdr, json={"parent_opt_in": True})
    assert approve.json()["data"]["parent_opt_in"] is True
    withdraw = await client.put(f"{ENROLLMENTS}/{eid}", headers=parent_hdr, json={"parent_opt_in": False})
    assert withdraw.json()["data"]["parent_opt_in"] is False


async def test_parent_bus_consent_separate(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    _, _, parent_hdr = await _parent_with_children(db_session, phone="+919863333333")
    await _enroll(client, admin_hdr, "+919863333333")
    eid = (await client.get(ENROLLMENTS, headers=parent_hdr)).json()["data"][0]["id"]

    resp = await client.put(f"{ENROLLMENTS}/{eid}", headers=parent_hdr, json={"bus_opt_in": True})
    data = resp.json()["data"]
    assert data["bus_opt_in"] is True
    assert data["parent_opt_in"] is False  # independent of school visibility


async def test_consent_requires_manage(client, db_session):
    _, _, admin_hdr = await _school_admin(db_session)
    # Parent (primary) enrolls; a view-only guardian must not be able to consent.
    parent, (child,), _ = await _parent_with_children(db_session, phone="+919864444444")
    await _enroll(client, admin_hdr, "+919864444444")
    eid = str((await db_session.execute(select(StudentEnrollment).where(StudentEnrollment.child_id == child.id))).scalar_one().id)

    guardian = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91")
    db_session.add(guardian)
    await db_session.flush()
    db_session.add(FamilyMember(
        child_id=child.id, user_id=guardian.id, role="guardian",
        is_primary=False, can_view=True, can_call=False, can_manage=False,
    ))
    await db_session.flush()
    g_hdr = {"Authorization": f"Bearer {create_access_token(str(guardian.id))}"}

    resp = await client.put(f"{ENROLLMENTS}/{eid}", headers=g_hdr, json={"parent_opt_in": True})
    assert resp.status_code == 403


async def test_consent_non_member_404(client, db_session, auth_headers):
    _, _, admin_hdr = await _school_admin(db_session)
    parent, (child,), _ = await _parent_with_children(db_session, phone="+919865555555")
    await _enroll(client, admin_hdr, "+919865555555")
    eid = str((await db_session.execute(select(StudentEnrollment).where(StudentEnrollment.child_id == child.id))).scalar_one().id)
    resp = await client.put(f"{ENROLLMENTS}/{eid}", headers=auth_headers, json={"parent_opt_in": True})
    assert resp.status_code == 404


async def test_consent_unknown_enrollment_404(client, db_session):
    _, _, parent_hdr = await _parent_with_children(db_session, phone="+919866666666")
    resp = await client.put(f"{ENROLLMENTS}/{uuid.uuid4()}", headers=parent_hdr, json={"parent_opt_in": True})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# The authorization backbone (require_enrolled_child)
# --------------------------------------------------------------------------- #
async def test_require_enrolled_child_gate(client, db_session):
    school, admin, _ = await _school_admin(db_session)
    _, (child,), _ = await _parent_with_children(db_session, phone="+919867777777")
    enr = StudentEnrollment(school_id=school.id, child_id=child.id, parent_opt_in=False)
    db_session.add(enr)
    await db_session.flush()
    svc = EnrollmentService(db_session)

    # Pending consent → gated (404).
    try:
        await svc.require_enrolled_child(admin, child.id)
        assert False, "expected 404"
    except APIException as exc:
        assert exc.status_code == 404 and exc.code == "CHILD_NOT_ENROLLED"

    # After opt-in → returns the enrollment.
    enr.parent_opt_in = True
    await db_session.flush()
    got = await svc.require_enrolled_child(admin, child.id)
    assert got.id == enr.id
