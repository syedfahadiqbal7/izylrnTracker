"""Tests for Emergency Contacts CRUD (Sprint 4 Slice 3) — Premium-gated."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.child import Child, FamilyMember
from app.models.sos import EmergencyContact
from app.models.user import User

CHILDREN = "/api/v1/children"
EC = "/api/v1/emergency-contacts"

CONTACT = {"name": "Grandma", "phone": "+919812345678", "relationship": "Grandmother"}


async def _setup(db, *, tier="premium"):
    parent = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91", subscription_tier=tier)
    db.add(parent)
    await db.flush()
    child = Child(name="Aryan")
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(parent.id))}"}
    return child, parent, headers


async def _add_member(db, child_id, *, can_manage=False):
    g = User(phone="+9198" + uuid.uuid4().hex[:8], country_code="+91")
    db.add(g)
    await db.flush()
    db.add(FamilyMember(
        child_id=child_id, user_id=g.id, role="guardian",
        is_primary=False, can_view=True, can_call=False, can_manage=can_manage,
    ))
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(str(g.id))}"}


async def _create(client, child_id, headers, payload=CONTACT):
    return await client.post(
        f"{CHILDREN}/{child_id}/emergency-contacts", headers=headers, json=payload
    )


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
async def test_create(client, db_session):
    child, _, headers = await _setup(db_session)
    resp = await _create(client, child.id, headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["name"] == "Grandma"
    assert data["relationship"] == "Grandmother"
    assert data["is_app_user"] is False  # no registered user with that phone


async def test_create_derives_app_user(client, db_session):
    child, _, headers = await _setup(db_session)
    db_session.add(User(phone="+919812345678", country_code="+91"))  # the contact has an account
    await db_session.flush()
    resp = await _create(client, child.id, headers)
    assert resp.json()["data"]["is_app_user"] is True


async def test_create_free_tier_blocked(client, db_session):
    child, _, headers = await _setup(db_session, tier="free")
    resp = await _create(client, child.id, headers)
    assert resp.status_code == 402
    assert resp.json()["code"] == "EMERGENCY_CONTACTS_REQUIRES_PREMIUM"


async def test_create_invalid_phone(client, db_session):
    child, _, headers = await _setup(db_session)
    resp = await _create(client, child.id, headers, {**CONTACT, "phone": "12345"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PHONE"


async def test_create_requires_manage(client, db_session):
    child, _, _ = await _setup(db_session)
    g_headers = await _add_member(db_session, child.id, can_manage=False)
    resp = await _create(client, child.id, g_headers)
    assert resp.status_code == 403


async def test_create_unknown_child_404(client, db_session):
    _, _, headers = await _setup(db_session)
    resp = await _create(client, uuid.uuid4(), headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_FOUND"


# --------------------------------------------------------------------------- #
# List / update / delete
# --------------------------------------------------------------------------- #
async def test_list(client, db_session):
    child, _, headers = await _setup(db_session)
    await _create(client, child.id, headers)
    await _create(client, child.id, headers, {"name": "Uncle", "phone": "+919812345679"})
    resp = await client.get(f"{CHILDREN}/{child.id}/emergency-contacts", headers=headers)
    assert resp.status_code == 200
    assert {c["name"] for c in resp.json()["data"]} == {"Grandma", "Uncle"}


async def test_update(client, db_session):
    child, _, headers = await _setup(db_session)
    cid = (await _create(client, child.id, headers)).json()["data"]["id"]
    resp = await client.put(
        f"{EC}/{cid}", headers=headers,
        json={"name": "Nani", "relationship": "Maternal Gran"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Nani"
    assert resp.json()["data"]["relationship"] == "Maternal Gran"


async def test_update_phone_rederives_app_user(client, db_session):
    child, _, headers = await _setup(db_session)
    cid = (await _create(client, child.id, headers)).json()["data"]["id"]
    # now a user registers with a new number, and we point the contact at it
    db_session.add(User(phone="+919800000022", country_code="+91"))
    await db_session.flush()
    resp = await client.put(f"{EC}/{cid}", headers=headers, json={"phone": "+919800000022"})
    assert resp.json()["data"]["is_app_user"] is True


async def test_delete(client, db_session):
    child, _, headers = await _setup(db_session)
    cid = (await _create(client, child.id, headers)).json()["data"]["id"]
    assert (await client.delete(f"{EC}/{cid}", headers=headers)).status_code == 200
    row = (await db_session.execute(
        select(EmergencyContact).where(EmergencyContact.id == uuid.UUID(cid))
    )).scalar_one_or_none()
    assert row is None


async def test_non_member_cannot_update_404(client, db_session):
    child, _, headers = await _setup(db_session)
    cid = (await _create(client, child.id, headers)).json()["data"]["id"]
    stranger = User(phone="+919822222222", country_code="+91")
    db_session.add(stranger)
    await db_session.flush()
    s_headers = {"Authorization": f"Bearer {create_access_token(str(stranger.id))}"}
    resp = await client.put(f"{EC}/{cid}", headers=s_headers, json={"name": "Hack"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "EMERGENCY_CONTACT_NOT_FOUND"
