"""Tests for parent device pairing & management (Sprint 11).

Covers pairing (+ Traccar registration wiring), IMEI uniqueness, the per-child device
tier limit, manage/view permissions, update validation, soft-delete + Traccar cleanup,
live online status, and the graceful seam when Traccar isn't configured.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core import redis_keys as rk
from app.core.security import create_access_token
from app.models.child import FamilyMember
from app.models.device import Device
from app.models.user import User

CHILDREN = "/api/v1/children"
DEVICES = "/api/v1/devices"

WATCH = {"name": "Aryan's Watch", "imei": "358900000000001", "device_type": "watch"}


async def _make_child(client, headers, name="Aryan") -> str:
    resp = await client.post(CHILDREN, headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _add_member(db, child_id, *, phone, can_view=True, can_manage=False):
    g = User(phone=phone, country_code="+91")
    db.add(g)
    await db.flush()
    db.add(
        FamilyMember(
            child_id=uuid.UUID(child_id), user_id=g.id, role="guardian",
            is_primary=False, can_view=can_view, can_call=False, can_manage=can_manage,
        )
    )
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(str(g.id))}"}


# ------------------------------------------------------------------- pairing
async def test_pair_device_success(client, auth_headers, fake_traccar_gateway):
    child_id = await _make_child(client, auth_headers)
    resp = await client.post(f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["name"] == "Aryan's Watch"
    assert data["device_type"] == "watch"
    assert data["traccar_id"] == 555          # from the fake registration
    assert data["is_online"] is False
    # Traccar was asked to register the tracker with its IMEI.
    assert fake_traccar_gateway.created_devices == [("358900000000001", "Aryan's Watch")]


async def test_pair_reflected_in_child_device_count(client, auth_headers):
    child_id = await _make_child(client, auth_headers)
    await client.post(f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH)
    got = await client.get(f"{CHILDREN}/{child_id}", headers=auth_headers)
    assert got.json()["data"]["device_count"] == 1


async def test_pair_duplicate_imei_conflicts(client, auth_headers, user, db_session):
    user.subscription_tier = "basic"  # room for a 2nd child + 2nd device, so IMEI is the gate
    await db_session.flush()
    child_id = await _make_child(client, auth_headers)
    await client.post(f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH)
    other = await _make_child(client, auth_headers, name="Sara")
    resp = await client.post(f"{CHILDREN}/{other}/devices", headers=auth_headers, json=WATCH)
    assert resp.status_code == 409
    assert resp.json()["code"] == "IMEI_TAKEN"


async def test_traccar_unconfigured_pairs_with_null_traccar_id(
    client, auth_headers, fake_traccar_gateway
):
    # Simulate Traccar not configured / registration failing → graceful null id.
    fake_traccar_gateway.next_device_id = None
    child_id = await _make_child(client, auth_headers)
    resp = await client.post(f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH)
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["traccar_id"] is None  # pairing still succeeded locally


# --------------------------------------------------------------- tier limits
async def test_free_tier_capped_at_one_device(client, auth_headers):
    child_id = await _make_child(client, auth_headers)
    first = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH
    )
    assert first.status_code == 201
    second = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers,
        json={"name": "Bag", "imei": "358900000000002", "device_type": "bag_tracker"},
    )
    assert second.status_code == 402
    assert second.json()["code"] == "DEVICE_LIMIT_REACHED"


async def test_basic_tier_allows_two_devices(client, auth_headers, user, db_session):
    user.subscription_tier = "basic"  # free caps at 1 device/child
    await db_session.flush()
    child_id = await _make_child(client, auth_headers)
    a = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH
    )
    b = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers,
        json={"name": "Bag", "imei": "358900000000002", "device_type": "bag_tracker"},
    )
    c = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers,
        json={"name": "Phone", "imei": "358900000000003", "device_type": "phone"},
    )
    assert a.status_code == 201 and b.status_code == 201
    assert c.status_code == 402  # third exceeds Basic's 2/child


# ---------------------------------------------------------------- permissions
async def test_non_member_gets_404(client, auth_headers, db_session):
    child_id = await _make_child(client, auth_headers)
    # A user with no membership on the child must not learn it exists → 404.
    other = User(phone="+919000000009", country_code="+91")
    db_session.add(other)
    await db_session.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
    resp = await client.post(f"{CHILDREN}/{child_id}/devices", headers=headers, json=WATCH)
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_FOUND"


async def test_guardian_without_manage_cannot_pair(client, auth_headers, db_session):
    child_id = await _make_child(client, auth_headers)
    guardian = await _add_member(db_session, child_id, phone="+919000000002", can_manage=False)
    resp = await client.post(f"{CHILDREN}/{child_id}/devices", headers=guardian, json=WATCH)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


async def test_guardian_with_view_can_list(client, auth_headers, db_session):
    child_id = await _make_child(client, auth_headers)
    await client.post(f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH)
    guardian = await _add_member(db_session, child_id, phone="+919000000003", can_view=True)
    resp = await client.get(f"{CHILDREN}/{child_id}/devices", headers=guardian)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


# ------------------------------------------------------------ list / get / online
async def test_list_shows_live_online_from_redis(client, auth_headers, redis_client):
    child_id = await _make_child(client, auth_headers)
    created = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH
    )
    device_id = created.json()["data"]["id"]
    await redis_client.set(rk.device_online(device_id), "1")
    resp = await client.get(f"{CHILDREN}/{child_id}/devices", headers=auth_headers)
    assert resp.json()["data"][0]["is_online"] is True


async def test_get_device(client, auth_headers):
    child_id = await _make_child(client, auth_headers)
    created = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH
    )
    device_id = created.json()["data"]["id"]
    resp = await client.get(f"{DEVICES}/{device_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == device_id


async def test_get_unknown_device_404(client, auth_headers):
    resp = await client.get(f"{DEVICES}/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "DEVICE_NOT_FOUND"


# ------------------------------------------------------------------- update
async def test_update_device_fields(client, auth_headers):
    child_id = await _make_child(client, auth_headers)
    created = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH
    )
    device_id = created.json()["data"]["id"]
    resp = await client.put(
        f"{DEVICES}/{device_id}", headers=auth_headers,
        json={"name": "Renamed", "battery_threshold": 30, "watch_removed_enabled": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == "Renamed"
    assert data["battery_threshold"] == 30
    assert data["watch_removed_enabled"] is True


async def test_update_rejects_invalid_threshold(client, auth_headers):
    child_id = await _make_child(client, auth_headers)
    created = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH
    )
    device_id = created.json()["data"]["id"]
    resp = await client.put(
        f"{DEVICES}/{device_id}", headers=auth_headers, json={"battery_threshold": 25}
    )
    assert resp.status_code == 422  # not in {10,15,20,30}


# ------------------------------------------------------------------- delete
async def test_delete_device_soft_deletes_and_cleans_traccar(
    client, auth_headers, db_session, fake_traccar_gateway
):
    child_id = await _make_child(client, auth_headers)
    created = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH
    )
    device_id = created.json()["data"]["id"]

    resp = await client.delete(f"{DEVICES}/{device_id}", headers=auth_headers)
    assert resp.status_code == 200

    # Removed from Traccar with the stored traccar_id.
    assert fake_traccar_gateway.deleted_devices == [555]
    # Gone from the list and the child's device count.
    listed = await client.get(f"{CHILDREN}/{child_id}/devices", headers=auth_headers)
    assert listed.json()["data"] == []
    # Soft-deleted, not hard-deleted.
    row = (
        await db_session.execute(select(Device).where(Device.id == uuid.UUID(device_id)))
    ).scalar_one()
    assert row.deleted_at is not None
    assert row.active is False


async def test_deleted_imei_still_reserved(client, auth_headers):
    # IMEI is globally unique incl. soft-deleted rows — re-pairing the same IMEI 409s.
    child_id = await _make_child(client, auth_headers)
    created = await client.post(
        f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH
    )
    await client.delete(f"{DEVICES}/{created.json()['data']['id']}", headers=auth_headers)
    again = await client.post(f"{CHILDREN}/{child_id}/devices", headers=auth_headers, json=WATCH)
    assert again.status_code == 409
    assert again.json()["code"] == "IMEI_TAKEN"
