"""Tests for the school-side Parents screen (Model 1 — admin manages parents).

Covers: listing parents of enrolled students (with their children), tenant isolation,
search, editing a parent's name, and removing a parent from the school (which deletes
their enrollments → revokes app access per the Model 1 login gate).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import create_access_token, hash_secret
from app.models.child import Child, FamilyMember
from app.models.school import School, SchoolAdmin, StudentEnrollment
from app.models.user import User

PARENTS = "/api/v1/schools/parents"


async def _school_admin(db, *, name="Green Valley", role="admin"):
    school = School(name=name, timezone="Asia/Dubai")
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


async def _enrolled_parent(db, school, *, name="Asha", child_names=("Aarav",)):
    parent = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91", name=name)
    db.add(parent)
    await db.flush()
    for cn in child_names:
        child = Child(name=cn)
        db.add(child)
        await db.flush()
        db.add(FamilyMember(
            child_id=child.id, user_id=parent.id, role="parent",
            is_primary=True, can_view=True, can_call=True, can_manage=True,
        ))
        db.add(StudentEnrollment(school_id=school.id, child_id=child.id))
    await db.flush()
    return parent


# --------------------------------------------------------------------------- list
async def test_list_parents_with_children(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    await _enrolled_parent(db_session, school, name="Asha", child_names=("Aarav", "Diya"))

    resp = await client.get(PARENTS, headers=hdr)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    p = data[0]
    assert p["name"] == "Asha"
    assert p["child_count"] == 2
    assert {c["name"] for c in p["children"]} == {"Aarav", "Diya"}


async def test_list_parents_tenant_isolation(client, db_session):
    school_a, _, hdr_a = await _school_admin(db_session, name="A")
    school_b, _, _ = await _school_admin(db_session, name="B")
    await _enrolled_parent(db_session, school_b, name="OtherSchoolParent")

    resp = await client.get(PARENTS, headers=hdr_a)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_list_parents_search(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    await _enrolled_parent(db_session, school, name="Zainab")
    await _enrolled_parent(db_session, school, name="Bilal")

    resp = await client.get(PARENTS, headers=hdr, params={"q": "zain"})
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["data"]]
    assert names == ["Zainab"]


# --------------------------------------------------------------------------- update
async def test_update_parent_name(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    parent = await _enrolled_parent(db_session, school, name="Old Name")

    resp = await client.put(f"{PARENTS}/{parent.id}", headers=hdr, json={"name": "New Name"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["name"] == "New Name"


async def test_update_parent_other_school_404(client, db_session):
    school_a, _, hdr_a = await _school_admin(db_session, name="A")
    school_b, _, _ = await _school_admin(db_session, name="B")
    parent = await _enrolled_parent(db_session, school_b, name="B Parent")

    resp = await client.put(f"{PARENTS}/{parent.id}", headers=hdr_a, json={"name": "X"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "PARENT_NOT_FOUND"


# --------------------------------------------------------------------------- remove
async def test_remove_parent_deletes_enrollments(client, db_session):
    school, _, hdr = await _school_admin(db_session)
    parent = await _enrolled_parent(db_session, school, child_names=("Aarav", "Diya"))

    resp = await client.delete(f"{PARENTS}/{parent.id}", headers=hdr)
    assert resp.status_code == 204, resp.text

    # No enrollments remain for this school → parent no longer listed / has no access.
    remaining = (
        await db_session.execute(
            select(StudentEnrollment).where(StudentEnrollment.school_id == school.id)
        )
    ).scalars().all()
    assert remaining == []
    # The user + children are retained (soft model), not hard-deleted.
    assert (await db_session.execute(select(User).where(User.id == parent.id))).scalar_one()


async def test_remove_parent_other_school_404(client, db_session):
    school_a, _, hdr_a = await _school_admin(db_session, name="A")
    school_b, _, _ = await _school_admin(db_session, name="B")
    parent = await _enrolled_parent(db_session, school_b)

    resp = await client.delete(f"{PARENTS}/{parent.id}", headers=hdr_a)
    assert resp.status_code == 404
