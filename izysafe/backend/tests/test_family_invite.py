"""Tests for guardian invite (send) + accept flow."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.alert import Alert
from app.models.child import FamilyMember, Invite
from app.models.user import User

PARENT_PHONE = "+919876543210"   # matches the `user` fixture
G1, G2, G3 = "+919811111111", "+919822222222", "+919833333333"


async def _basic_parent(user, db_session):
    user.subscription_tier = "basic"   # free tier allows 0 guardians
    await db_session.flush()


async def _make_child(client, auth_headers, name="Aryan") -> str:
    r = await client.post("/api/v1/children", headers=auth_headers, json={"name": name})
    return r.json()["data"]["id"]


async def _invite(client, headers, child_id, phone, **extra):
    return await client.post(
        f"/api/v1/children/{child_id}/family/invite",
        headers=headers,
        json={"phone": phone, **extra},
    )


def _token_of(resp) -> str:
    return resp.json()["data"]["invite_link"].rsplit("/", 1)[-1]


async def _make_user(db, phone) -> tuple[User, dict]:
    u = User(phone=phone, country_code="+91")
    db.add(u)
    await db.flush()
    return u, {"Authorization": f"Bearer {create_access_token(str(u.id))}"}


# --------------------------------------------------------------------------- #
# Invite (send)
# --------------------------------------------------------------------------- #
async def test_invite_success(client, auth_headers, user, db_session, fake_invite_gateway):
    await _basic_parent(user, db_session)
    cid = await _make_child(client, auth_headers)
    resp = await _invite(client, auth_headers, cid, G1, role="grandparent", can_call=True)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["phone"] == G1
    assert data["role"] == "grandparent"
    assert data["can_call"] is True
    assert data["channel"] == "whatsapp"
    assert data["invite_link"].endswith(_token_of(resp))
    assert len(fake_invite_gateway.calls) == 1

    inv = (
        await db_session.execute(select(Invite).where(Invite.child_id == uuid.UUID(cid)))
    ).scalar_one()
    assert inv.phone == G1 and inv.accepted is False


async def test_invite_free_tier_blocked(client, auth_headers):
    # default user is free tier → no guardians allowed
    cid = await _make_child(client, auth_headers)
    resp = await _invite(client, auth_headers, cid, G1)
    assert resp.status_code == 402
    assert resp.json()["code"] == "GUARDIAN_LIMIT_REACHED"
    assert "Basic" in resp.json()["message"]


async def test_invite_self_blocked(client, auth_headers, user, db_session):
    await _basic_parent(user, db_session)
    cid = await _make_child(client, auth_headers)
    resp = await _invite(client, auth_headers, cid, PARENT_PHONE)
    assert resp.status_code == 400
    assert resp.json()["code"] == "CANNOT_INVITE_SELF"


async def test_invite_already_member(client, auth_headers, user, db_session):
    await _basic_parent(user, db_session)
    cid = await _make_child(client, auth_headers)
    member, _ = await _make_user(db_session, G1)
    db_session.add(
        FamilyMember(child_id=uuid.UUID(cid), user_id=member.id, role="guardian", can_view=True)
    )
    await db_session.flush()
    resp = await _invite(client, auth_headers, cid, G1)
    assert resp.status_code == 400
    assert resp.json()["code"] == "ALREADY_MEMBER"


async def test_invite_duplicate_pending(client, auth_headers, user, db_session):
    await _basic_parent(user, db_session)
    cid = await _make_child(client, auth_headers)
    assert (await _invite(client, auth_headers, cid, G1)).status_code == 201
    dup = await _invite(client, auth_headers, cid, G1)
    assert dup.status_code == 400
    assert dup.json()["code"] == "INVITE_ALREADY_SENT"


async def test_guardian_limit_counts_pending(client, auth_headers, user, db_session):
    await _basic_parent(user, db_session)        # basic = 2 guardians
    cid = await _make_child(client, auth_headers)
    assert (await _invite(client, auth_headers, cid, G1)).status_code == 201
    assert (await _invite(client, auth_headers, cid, G2)).status_code == 201
    blocked = await _invite(client, auth_headers, cid, G3)
    assert blocked.status_code == 402
    assert blocked.json()["code"] == "GUARDIAN_LIMIT_REACHED"


async def test_invite_requires_manage(client, auth_headers, user, db_session):
    await _basic_parent(user, db_session)
    cid = await _make_child(client, auth_headers)
    # a guardian WITHOUT manage cannot invite
    guardian, g_headers = await _make_user(db_session, G2)
    db_session.add(
        FamilyMember(
            child_id=uuid.UUID(cid), user_id=guardian.id, role="guardian",
            can_view=True, can_manage=False,
        )
    )
    await db_session.flush()
    resp = await _invite(client, g_headers, cid, G3)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


async def test_invite_delivery_failure_nonfatal(client, auth_headers, user, db_session, fake_invite_gateway):
    await _basic_parent(user, db_session)
    fake_invite_gateway.channel = None       # simulate WhatsApp + SMS both failing
    cid = await _make_child(client, auth_headers)
    resp = await _invite(client, auth_headers, cid, G1)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["channel"] is None
    assert data["invite_link"]               # manual-share link still returned
    # invite persisted despite delivery failure
    assert (
        await db_session.execute(select(Invite).where(Invite.child_id == uuid.UUID(cid)))
    ).scalar_one()


async def test_invite_requires_auth(client):
    resp = await client.post(
        f"/api/v1/children/{uuid.uuid4()}/family/invite", json={"phone": G1}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_MISSING"


# --------------------------------------------------------------------------- #
# Accept
# --------------------------------------------------------------------------- #
async def test_accept_success(client, auth_headers, user, db_session):
    await _basic_parent(user, db_session)
    cid = await _make_child(client, auth_headers)
    token = _token_of(await _invite(client, auth_headers, cid, G1, can_call=True))

    _, g_headers = await _make_user(db_session, G1)
    resp = await client.post(f"/api/v1/invites/{token}/accept", headers=g_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["child_id"] == cid
    assert data["child_name"] == "Aryan"
    assert data["role"] == "guardian"
    assert data["can_call"] is True

    # membership created + invite consumed
    fm = (
        await db_session.execute(
            select(FamilyMember).where(FamilyMember.child_id == uuid.UUID(cid))
        )
    ).scalars().all()
    assert any(not m.is_primary and m.can_call for m in fm)
    inv = (await db_session.execute(select(Invite).where(Invite.token == token))).scalar_one()
    assert inv.accepted is True

    # the new guardian can now view the child
    assert (await client.get(f"/api/v1/children/{cid}", headers=g_headers)).status_code == 200


async def test_accept_notifies_inviter(client, auth_headers, user, db_session, fake_fcm_gateway):
    await _basic_parent(user, db_session)
    user.fcm_token = "inviter-tok"          # inviter (primary parent) has a device
    cid = await _make_child(client, auth_headers)
    token = _token_of(await _invite(client, auth_headers, cid, G1))

    guardian, g_headers = await _make_user(db_session, G1)
    guardian.name = "Nani"
    await db_session.flush()
    resp = await client.post(f"/api/v1/invites/{token}/accept", headers=g_headers)
    assert resp.status_code == 200

    # the inviter got a family_join inbox row...
    alert = (
        await db_session.execute(select(Alert).where(Alert.user_id == user.id))
    ).scalar_one()
    assert alert.type == "family_join"
    assert "Nani" in alert.body
    # ...and an FCM push to their token
    assert fake_fcm_gateway.calls[-1]["tokens"] == ["inviter-tok"]
    assert fake_fcm_gateway.calls[-1]["data"]["type"] == "family_join"


async def test_accept_phone_mismatch(client, auth_headers, user, db_session):
    await _basic_parent(user, db_session)
    cid = await _make_child(client, auth_headers)
    token = _token_of(await _invite(client, auth_headers, cid, G1))
    # a different phone tries to accept
    _, other_headers = await _make_user(db_session, G2)
    resp = await client.post(f"/api/v1/invites/{token}/accept", headers=other_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "INVITE_PHONE_MISMATCH"


async def test_accept_unknown_token(client, db_session):
    _, headers = await _make_user(db_session, G1)
    resp = await client.post(f"/api/v1/invites/{secrets.token_hex(16)}/accept", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "INVITE_NOT_FOUND"


async def test_accept_expired(client, auth_headers, user, db_session):
    await _basic_parent(user, db_session)
    cid = await _make_child(client, auth_headers)
    invitee, headers = await _make_user(db_session, G1)
    token = secrets.token_hex(32)
    db_session.add(
        Invite(
            child_id=uuid.UUID(cid), invited_by=user.id, phone=G1, role="guardian",
            token=token, expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    await db_session.flush()
    resp = await client.post(f"/api/v1/invites/{token}/accept", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVITE_EXPIRED"


async def test_accept_already_used(client, auth_headers, user, db_session):
    await _basic_parent(user, db_session)
    cid = await _make_child(client, auth_headers)
    token = _token_of(await _invite(client, auth_headers, cid, G1))
    _, headers = await _make_user(db_session, G1)
    assert (await client.post(f"/api/v1/invites/{token}/accept", headers=headers)).status_code == 200
    again = await client.post(f"/api/v1/invites/{token}/accept", headers=headers)
    assert again.status_code == 400
    assert again.json()["code"] == "INVITE_ALREADY_USED"
