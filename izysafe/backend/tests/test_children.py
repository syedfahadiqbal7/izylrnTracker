"""Tests for Children CRUD: ownership, tier limits, permissions, soft delete."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.child import Child, FamilyMember
from app.models.user import User

BASE = "/api/v1/children"


async def _create(client, headers, name="Aryan"):
    return await client.post(BASE, headers=headers, json={"name": name})


async def _add_member(db, child_id, *, phone, can_view=True, can_manage=False, is_primary=False):
    g = User(phone=phone, country_code="+91")
    db.add(g)
    await db.flush()
    db.add(
        FamilyMember(
            child_id=child_id, user_id=g.id, role="guardian",
            is_primary=is_primary, can_view=can_view, can_call=False, can_manage=can_manage,
        )
    )
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(str(g.id))}"}


# --------------------------------------------------------------------------- #
# Create + ownership
# --------------------------------------------------------------------------- #
async def test_create_child_makes_primary_parent(client, auth_headers, user, db_session):
    resp = await _create(client, auth_headers, "Aryan")
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == "Aryan"
    assert data["device_count"] == 0
    assert data["permissions"] == {
        "role": "parent", "is_primary": True,
        "can_view": True, "can_call": True, "can_manage": True,
    }

    # a family_members row links creator → child as primary parent
    fm = (
        await db_session.execute(
            select(FamilyMember).where(
                FamilyMember.user_id == user.id, FamilyMember.child_id == uuid.UUID(data["id"])
            )
        )
    ).scalar_one()
    assert fm.is_primary is True and fm.role == "parent"


async def test_create_requires_auth(client):
    resp = await client.post(BASE, json={"name": "Aryan"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_MISSING"


async def test_create_invalid_name(client, auth_headers):
    resp = await client.post(BASE, headers=auth_headers, json={"name": "A"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- #
# List / detail
# --------------------------------------------------------------------------- #
async def test_list_children(client, auth_headers, user, db_session):
    user.subscription_tier = "premium"   # free tier caps at 1 child
    await db_session.flush()
    await _create(client, auth_headers, "Aryan")
    await _create(client, auth_headers, "Zara")
    resp = await client.get(BASE, headers=auth_headers)
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["data"]}
    assert names == {"Aryan", "Zara"}


async def test_get_child_detail(client, auth_headers):
    cid = (await _create(client, auth_headers)).json()["data"]["id"]
    resp = await client.get(f"{BASE}/{cid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["permissions"]["is_primary"] is True


async def test_get_unknown_child_404(client, auth_headers):
    resp = await client.get(f"{BASE}/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #
async def test_update_child(client, auth_headers):
    cid = (await _create(client, auth_headers)).json()["data"]["id"]
    resp = await client.put(
        f"{BASE}/{cid}", headers=auth_headers,
        json={"name": "Aryan Khan", "school_mode_enabled": True, "speed_threshold_kmh": 80},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Aryan Khan"
    assert data["school_mode_enabled"] is True
    assert data["speed_threshold_kmh"] == 80


async def test_update_invalid_speed_threshold(client, auth_headers):
    cid = (await _create(client, auth_headers)).json()["data"]["id"]
    resp = await client.put(f"{BASE}/{cid}", headers=auth_headers, json={"speed_threshold_kmh": 55})
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- #
# Soft delete
# --------------------------------------------------------------------------- #
async def test_soft_delete_child(client, auth_headers, db_session):
    cid = (await _create(client, auth_headers)).json()["data"]["id"]
    resp = await client.delete(f"{BASE}/{cid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["success"] is True

    # gone from detail + list
    assert (await client.get(f"{BASE}/{cid}", headers=auth_headers)).status_code == 404
    assert (await client.get(BASE, headers=auth_headers)).json()["data"] == []

    # but the row is retained with deleted_at set (30-day retention)
    child = (
        await db_session.execute(select(Child).where(Child.id == uuid.UUID(cid)))
    ).scalar_one()
    assert child.deleted_at is not None
    assert child.active is False


# --------------------------------------------------------------------------- #
# Tier limits
# --------------------------------------------------------------------------- #
async def test_free_tier_limit(client, auth_headers):
    assert (await _create(client, auth_headers, "One")).status_code == 201
    blocked = await _create(client, auth_headers, "Two")
    assert blocked.status_code == 402
    body = blocked.json()
    assert body["code"] == "CHILD_LIMIT_REACHED"
    assert "Basic" in body["message"]


async def test_basic_tier_limit(client, auth_headers, user, db_session):
    user.subscription_tier = "basic"
    await db_session.flush()
    for name in ("Aa", "Bb", "Cc"):
        assert (await _create(client, auth_headers, name)).status_code == 201
    blocked = await _create(client, auth_headers, "Dd")
    assert blocked.status_code == 402
    assert "Premium" in blocked.json()["message"]


async def test_premium_unlimited(client, auth_headers, user, db_session):
    user.subscription_tier = "premium"
    await db_session.flush()
    for i in range(5):
        assert (await _create(client, auth_headers, f"Kid{i}")).status_code == 201


# --------------------------------------------------------------------------- #
# Permissions (multi-user)
# --------------------------------------------------------------------------- #
async def test_non_member_cannot_see_child(client, auth_headers, db_session):
    cid = (await _create(client, auth_headers)).json()["data"]["id"]
    # a brand-new user with no membership
    stranger = User(phone="+919822222222", country_code="+91")
    db_session.add(stranger)
    await db_session.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(stranger.id))}"}
    resp = await client.get(f"{BASE}/{cid}", headers=headers)
    assert resp.status_code == 404  # not 403 — don't reveal existence
    assert resp.json()["code"] == "CHILD_NOT_FOUND"


async def test_guardian_can_view_but_not_manage(client, auth_headers, db_session):
    cid = (await _create(client, auth_headers)).json()["data"]["id"]
    g_headers = await _add_member(
        db_session, uuid.UUID(cid), phone="+919833333333", can_view=True, can_manage=False
    )
    # can view
    assert (await client.get(f"{BASE}/{cid}", headers=g_headers)).status_code == 200
    # cannot update
    upd = await client.put(f"{BASE}/{cid}", headers=g_headers, json={"name": "Hacked"})
    assert upd.status_code == 403
    assert upd.json()["code"] == "FORBIDDEN"


async def test_only_primary_can_delete(client, auth_headers, db_session):
    cid = (await _create(client, auth_headers)).json()["data"]["id"]
    # guardian WITH manage but NOT primary
    g_headers = await _add_member(
        db_session, uuid.UUID(cid), phone="+919844444444", can_view=True, can_manage=True, is_primary=False
    )
    resp = await client.delete(f"{BASE}/{cid}", headers=g_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"
