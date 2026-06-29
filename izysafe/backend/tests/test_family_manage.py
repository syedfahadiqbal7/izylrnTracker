"""Tests for family list / update-permissions / remove + invite management."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.child import FamilyMember, Invite
from app.models.user import User

G1, G2 = "+919811111111", "+919822222222"


async def _make_child(client, auth_headers, name="Aryan") -> str:
    r = await client.post("/api/v1/children", headers=auth_headers, json={"name": name})
    return r.json()["data"]["id"]


async def _add_member(db, child_id, phone, *, can_view=True, can_manage=False, role="guardian"):
    u = User(phone=phone, country_code="+91", name="Guardian")
    db.add(u)
    await db.flush()
    fm = FamilyMember(
        child_id=uuid.UUID(child_id), user_id=u.id, role=role,
        is_primary=False, can_view=can_view, can_call=False, can_manage=can_manage,
    )
    db.add(fm)
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    return u, fm, headers


async def _primary_member_id(db, child_id) -> str:
    fm = (
        await db.execute(
            select(FamilyMember).where(
                FamilyMember.child_id == uuid.UUID(child_id), FamilyMember.is_primary.is_(True)
            )
        )
    ).scalar_one()
    return str(fm.id)


# --------------------------------------------------------------------------- #
# List
# --------------------------------------------------------------------------- #
async def test_list_family(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    await _add_member(db_session, cid, G1)
    resp = await client.get(f"/api/v1/children/{cid}/family", headers=auth_headers)
    assert resp.status_code == 200
    members = resp.json()["data"]
    assert len(members) == 2
    assert members[0]["is_primary"] is True          # primary listed first
    assert {m["phone"] for m in members} == {"+919876543210", G1}


async def test_list_family_non_member_404(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    other = User(phone=G2, country_code="+91")   # not a member of this child
    db_session.add(other)
    await db_session.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
    resp = await client.get(f"/api/v1/children/{cid}/family", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Update permissions
# --------------------------------------------------------------------------- #
async def test_update_member_permissions(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    _, fm, _ = await _add_member(db_session, cid, G1, can_manage=False)
    resp = await client.put(
        f"/api/v1/children/{cid}/family/{fm.id}",
        headers=auth_headers,
        json={"can_manage": True, "can_call": True, "role": "teacher"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["can_manage"] is True and data["can_call"] is True and data["role"] == "teacher"
    await db_session.refresh(fm)
    assert fm.can_manage is True


async def test_update_primary_protected(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    pid = await _primary_member_id(db_session, cid)
    resp = await client.put(
        f"/api/v1/children/{cid}/family/{pid}", headers=auth_headers, json={"can_manage": False}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "PRIMARY_PROTECTED"


async def test_update_requires_manage(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    _, target_fm, _ = await _add_member(db_session, cid, G1)
    _, _, viewer_headers = await _add_member(db_session, cid, G2, can_manage=False)
    resp = await client.put(
        f"/api/v1/children/{cid}/family/{target_fm.id}", headers=viewer_headers,
        json={"can_manage": True},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


async def test_update_member_not_found(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    resp = await client.put(
        f"/api/v1/children/{cid}/family/{uuid.uuid4()}", headers=auth_headers,
        json={"can_call": True},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "MEMBER_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Remove
# --------------------------------------------------------------------------- #
async def test_manager_removes_guardian(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    _, fm, g_headers = await _add_member(db_session, cid, G1)
    resp = await client.delete(f"/api/v1/children/{cid}/family/{fm.id}", headers=auth_headers)
    assert resp.status_code == 200
    # guardian loses access
    assert (await client.get(f"/api/v1/children/{cid}", headers=g_headers)).status_code == 404


async def test_remove_primary_protected(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    pid = await _primary_member_id(db_session, cid)
    resp = await client.delete(f"/api/v1/children/{cid}/family/{pid}", headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "PRIMARY_PROTECTED"


async def test_self_removal_allowed_without_manage(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    _, fm, g_headers = await _add_member(db_session, cid, G1, can_manage=False)
    # the guardian removes THEMSELVES (no manage needed)
    resp = await client.delete(f"/api/v1/children/{cid}/family/{fm.id}", headers=g_headers)
    assert resp.status_code == 200
    assert (await client.get(f"/api/v1/children/{cid}", headers=g_headers)).status_code == 404


async def test_remove_other_requires_manage(client, auth_headers, db_session):
    cid = await _make_child(client, auth_headers)
    _, target_fm, _ = await _add_member(db_session, cid, G1)
    _, _, viewer_headers = await _add_member(db_session, cid, G2, can_manage=False)
    resp = await client.delete(
        f"/api/v1/children/{cid}/family/{target_fm.id}", headers=viewer_headers
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# --------------------------------------------------------------------------- #
# Invite management
# --------------------------------------------------------------------------- #
async def _basic(user, db):
    user.subscription_tier = "basic"
    await db.flush()


async def test_list_pending_invites(client, auth_headers, user, db_session):
    await _basic(user, db_session)
    cid = await _make_child(client, auth_headers)
    await client.post(f"/api/v1/children/{cid}/family/invite", headers=auth_headers, json={"phone": G1})
    resp = await client.get(f"/api/v1/children/{cid}/invites", headers=auth_headers)
    assert resp.status_code == 200
    invites = resp.json()["data"]
    assert len(invites) == 1
    assert invites[0]["phone"] == G1 and invites[0]["expired"] is False


async def test_revoke_pending_invite(client, auth_headers, user, db_session):
    await _basic(user, db_session)
    cid = await _make_child(client, auth_headers)
    inv = await client.post(
        f"/api/v1/children/{cid}/family/invite", headers=auth_headers, json={"phone": G1}
    )
    token = inv.json()["data"]["invite_link"].rsplit("/", 1)[-1]
    resp = await client.delete(f"/api/v1/invites/{token}", headers=auth_headers)
    assert resp.status_code == 200
    # gone from the pending list
    listing = await client.get(f"/api/v1/children/{cid}/invites", headers=auth_headers)
    assert listing.json()["data"] == []


async def test_revoke_accepted_invite_fails(client, auth_headers, user, db_session):
    await _basic(user, db_session)
    cid = await _make_child(client, auth_headers)
    inv = await client.post(
        f"/api/v1/children/{cid}/family/invite", headers=auth_headers, json={"phone": G1}
    )
    token = inv.json()["data"]["invite_link"].rsplit("/", 1)[-1]
    # invitee accepts
    guest = User(phone=G1, country_code="+91")
    db_session.add(guest)
    await db_session.flush()
    g_headers = {"Authorization": f"Bearer {create_access_token(str(guest.id))}"}
    assert (await client.post(f"/api/v1/invites/{token}/accept", headers=g_headers)).status_code == 200
    # revoking an accepted invite is rejected
    resp = await client.delete(f"/api/v1/invites/{token}", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVITE_ALREADY_USED"


async def test_revoke_unknown_invite(client, auth_headers):
    resp = await client.delete("/api/v1/invites/deadbeef", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "INVITE_NOT_FOUND"
