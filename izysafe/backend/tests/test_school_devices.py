"""Tests for school-provisioned student devices (admin-side device pairing).

A school admin can equip a student *enrolled at their school* with a GPS device:
  POST/GET  /schools/students/{child_id}/devices
  DELETE    /schools/students/devices/{device_id}

Covers: enrollment-based authorization (404 for non-enrolled / other-school children —
tenant isolation), Traccar registration wiring, IMEI uniqueness, NO per-child tier limit
(product decision — the school provisions its own trackers), list, and soft-delete +
Traccar cleanup.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import create_access_token, hash_secret
from app.models.child import Child, FamilyMember
from app.models.device import Device
from app.models.school import School, SchoolAdmin, StudentEnrollment
from app.models.user import User


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
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


async def _child_with_primary(db, *, name="Aryan", tier="free"):
    parent = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91", subscription_tier=tier)
    db.add(parent)
    await db.flush()
    child = Child(name=name)
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    await db.flush()
    return parent, child


async def _enroll(db, school, child, **opts):
    e = StudentEnrollment(school_id=school.id, child_id=child.id, **opts)
    db.add(e)
    await db.flush()
    return e


def _url(child_id) -> str:
    return f"/api/v1/schools/students/{child_id}/devices"


TAG = {"name": "School Tag", "imei": "860000000000001"}


# --------------------------------------------------------------------------- #
# Add
# --------------------------------------------------------------------------- #
async def test_admin_adds_device_to_enrolled_student(client, db_session, fake_traccar_gateway):
    school, _, hdr = await _school_admin(db_session)
    _, child = await _child_with_primary(db_session)
    await _enroll(db_session, school, child)

    resp = await client.post(_url(child.id), headers=hdr, json=TAG)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["name"] == "School Tag"
    assert data["child_id"] == str(child.id)
    assert data["traccar_id"] == 555               # from the fake registration
    # Registered in Traccar with the IMEI the admin entered.
    assert fake_traccar_gateway.created_devices == [("860000000000001", "School Tag")]


async def test_admin_add_bypasses_tier_limit(client, db_session, fake_traccar_gateway):
    """Free tier = 1 device/child for parents, but admin-added school devices have NO limit."""
    school, _, hdr = await _school_admin(db_session)
    _, child = await _child_with_primary(db_session, tier="free")
    await _enroll(db_session, school, child)

    r1 = await client.post(_url(child.id), headers=hdr, json={"name": "Tag 1", "imei": "860000000000010"})
    r2 = await client.post(_url(child.id), headers=hdr, json={"name": "Tag 2", "imei": "860000000000011"})
    r3 = await client.post(_url(child.id), headers=hdr, json={"name": "Tag 3", "imei": "860000000000012"})
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text   # would be 402 under the parent tier gate
    assert r3.status_code == 201, r3.text


async def test_add_duplicate_imei_rejected(client, db_session, fake_traccar_gateway):
    school, _, hdr = await _school_admin(db_session)
    _, child = await _child_with_primary(db_session)
    await _enroll(db_session, school, child)

    assert (await client.post(_url(child.id), headers=hdr, json=TAG)).status_code == 201
    dup = await client.post(_url(child.id), headers=hdr, json={"name": "Dup", "imei": TAG["imei"]})
    assert dup.status_code == 409
    assert dup.json()["code"] == "IMEI_TAKEN"


# --------------------------------------------------------------------------- #
# Authorization / tenant isolation
# --------------------------------------------------------------------------- #
async def test_add_to_unenrolled_child_404(client, db_session, fake_traccar_gateway):
    _, _, hdr = await _school_admin(db_session)
    _, child = await _child_with_primary(db_session)      # exists but NOT enrolled
    resp = await client.post(_url(child.id), headers=hdr, json=TAG)
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_FOUND"
    assert fake_traccar_gateway.created_devices == []     # never touched Traccar


async def test_add_to_other_schools_student_404(client, db_session, fake_traccar_gateway):
    school_a, _, hdr_a = await _school_admin(db_session, name="A")
    school_b, _, _ = await _school_admin(db_session, name="B")
    _, child = await _child_with_primary(db_session)
    await _enroll(db_session, school_b, child)            # enrolled at B, not A

    resp = await client.post(_url(child.id), headers=hdr_a, json=TAG)
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_FOUND"


# --------------------------------------------------------------------------- #
# List
# --------------------------------------------------------------------------- #
async def test_list_student_devices(client, db_session, fake_traccar_gateway):
    school, _, hdr = await _school_admin(db_session)
    _, child = await _child_with_primary(db_session)
    await _enroll(db_session, school, child)
    await client.post(_url(child.id), headers=hdr, json=TAG)

    resp = await client.get(_url(child.id), headers=hdr)
    assert resp.status_code == 200, resp.text
    names = [d["name"] for d in resp.json()["data"]]
    assert names == ["School Tag"]


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #
async def test_remove_student_device(client, db_session, fake_traccar_gateway):
    school, _, hdr = await _school_admin(db_session)
    _, child = await _child_with_primary(db_session)
    await _enroll(db_session, school, child)
    add = await client.post(_url(child.id), headers=hdr, json=TAG)
    device_id = add.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/schools/students/devices/{device_id}", headers=hdr)
    assert resp.status_code == 204, resp.text
    # Removed from Traccar (best-effort) + soft-deleted locally.
    assert fake_traccar_gateway.deleted_devices == [555]
    row = (
        await db_session.execute(select(Device).where(Device.id == uuid.UUID(device_id)))
    ).scalar_one()
    assert row.deleted_at is not None
    assert row.active is False


async def test_remove_other_schools_device_404(client, db_session, fake_traccar_gateway):
    school_a, _, hdr_a = await _school_admin(db_session, name="A")
    school_b, _, hdr_b = await _school_admin(db_session, name="B")
    _, child = await _child_with_primary(db_session)
    await _enroll(db_session, school_b, child)
    add = await client.post(_url(child.id), headers=hdr_b, json=TAG)
    device_id = add.json()["data"]["id"]

    # Admin A cannot delete a device on B's enrolled student.
    resp = await client.delete(f"/api/v1/schools/students/devices/{device_id}", headers=hdr_a)
    assert resp.status_code == 404
