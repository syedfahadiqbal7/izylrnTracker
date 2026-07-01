"""Tests for Chat (Sprint 7 Slice 6, F23) — Basic+, hardware-gated dispatch.

Covers send (parent→watch): tier gate, membership, content validation, and the
best-effort dispatch status (online watch → sent, offline/none → queued); list history;
and the inbound message webhook (watch→parent): store as the child + `chat_reply`
fan-out, secret auth, unknown-device + free-tier drops.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.security import create_access_token
from app.models.alert import Alert
from app.models.child import Child, FamilyMember
from app.models.comms import ChatMessage
from app.models.device import Device
from app.models.user import User

CHILDREN = "/api/v1/children"
MESSAGE_WEBHOOK = "/api/v1/webhook/traccar/message"
SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}


async def _setup(db, *, tier="basic", watch=False, traccar_id=None):
    parent = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91",
        subscription_tier=tier, fcm_token="parent-tok",
    )
    db.add(parent)
    await db.flush()
    child = Child(name="Aryan")
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    dev = None
    if watch:
        dev = Device(
            child_id=child.id, name="Aryan Watch", device_type="watch",
            imei=uuid.uuid4().hex[:15], traccar_id=traccar_id,
        )
        db.add(dev)
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(str(parent.id))}"}
    return child, parent, headers, dev


async def _send(client, child_id, headers, content="On my way!"):
    return await client.post(f"{CHILDREN}/{child_id}/chat", headers=headers, json={"content": content})


async def _count_messages(db, child_id, sender_type=None):
    stmt = select(func.count()).select_from(ChatMessage).where(ChatMessage.child_id == child_id)
    if sender_type:
        stmt = stmt.where(ChatMessage.sender_type == sender_type)
    return (await db.execute(stmt)).scalar_one()


# --------------------------------------------------------------------------- #
# Send (parent → watch)
# --------------------------------------------------------------------------- #
async def test_send_no_watch_queued(client, db_session):
    child, _, headers, _ = await _setup(db_session)
    resp = await _send(client, child.id, headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["sender_type"] == "parent"
    assert data["status"] == "queued"  # no watch to dispatch to
    assert data["content"] == "On my way!"


async def test_send_online_watch_dispatched(client, db_session, redis_client, fake_traccar_gateway):
    child, _, headers, dev = await _setup(db_session, watch=True, traccar_id=701)
    await redis_client.set(rk.device_online(dev.id), "1")
    resp = await _send(client, child.id, headers, "Come home")
    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "sent"
    assert fake_traccar_gateway.text_calls == [(701, "Come home")]


async def test_send_offline_watch_queued(client, db_session, redis_client, fake_traccar_gateway):
    child, _, headers, dev = await _setup(db_session, watch=True, traccar_id=702)
    # not marked online
    resp = await _send(client, child.id, headers)
    assert resp.json()["data"]["status"] == "queued"
    assert fake_traccar_gateway.text_calls == []


async def test_send_free_tier_blocked(client, db_session):
    child, _, headers, _ = await _setup(db_session, tier="free")
    resp = await _send(client, child.id, headers)
    assert resp.status_code == 402
    assert resp.json()["code"] == "CHAT_REQUIRES_BASIC"


async def test_send_non_member_404(client, db_session, auth_headers):
    child, _, _, _ = await _setup(db_session)
    resp = await _send(client, child.id, auth_headers)
    assert resp.status_code == 404


async def test_send_empty_content_rejected(client, db_session):
    child, _, headers, _ = await _setup(db_session)
    resp = await _send(client, child.id, headers, "")
    assert resp.status_code == 422


async def test_send_too_long_content_rejected(client, db_session):
    child, _, headers, _ = await _setup(db_session)
    resp = await _send(client, child.id, headers, "x" * 121)
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# List
# --------------------------------------------------------------------------- #
async def test_list_history(client, db_session):
    child, parent, headers, _ = await _setup(db_session)
    # Explicit distinct timestamps: within one test transaction Postgres NOW() is
    # constant, so seed created_at directly to assert the most-recent-first order.
    base = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
    db_session.add(ChatMessage(
        child_id=child.id, sender_type="parent", sender_id=parent.id,
        content="first", status="sent", created_at=base,
    ))
    db_session.add(ChatMessage(
        child_id=child.id, sender_type="parent", sender_id=parent.id,
        content="second", status="sent", created_at=base + timedelta(minutes=1),
    ))
    await db_session.flush()

    resp = await client.get(f"{CHILDREN}/{child.id}/chat", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total"] == 2
    assert data["data"][0]["content"] == "second"  # most recent first
    assert data["data"][1]["content"] == "first"


async def test_list_non_member_404(client, db_session, auth_headers):
    child, _, _, _ = await _setup(db_session)
    resp = await client.get(f"{CHILDREN}/{child.id}/chat", headers=auth_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Inbound message webhook (watch → parent)
# --------------------------------------------------------------------------- #
def _inbound(traccar_id, imei, content="I'm here"):
    return {"deviceId": traccar_id, "uniqueId": imei, "content": content}


async def test_webhook_message_stores_and_notifies(client, db_session, fake_fcm_gateway):
    child, _, _, dev = await _setup(db_session, watch=True, traccar_id=711)
    resp = await client.post(MESSAGE_WEBHOOK, headers=SECRET_HEADERS,
                             json=_inbound(711, dev.imei, "Reached school"))
    assert resp.status_code == 200
    assert resp.json()["kind"] == "chat"

    assert await _count_messages(db_session, child.id, "child") == 1
    msg = (
        await db_session.execute(
            select(ChatMessage).where(ChatMessage.child_id == child.id)
        )
    ).scalars().one()
    assert msg.content == "Reached school"
    assert msg.status == "delivered"
    assert msg.sender_id is None
    # family notified
    alerts = (
        await db_session.execute(
            select(func.count()).select_from(Alert).where(
                Alert.child_id == child.id, Alert.type == "chat_reply"
            )
        )
    ).scalar_one()
    assert alerts == 1
    assert fake_fcm_gateway.calls[-1]["data"]["type"] == "chat_reply"


async def test_webhook_message_requires_secret(client, db_session):
    _, _, _, dev = await _setup(db_session, watch=True, traccar_id=712)
    resp = await client.post(MESSAGE_WEBHOOK, json=_inbound(712, dev.imei))
    assert resp.status_code == 401


async def test_webhook_message_unknown_device_ignored(client, db_session):
    resp = await client.post(MESSAGE_WEBHOOK, headers=SECRET_HEADERS,
                             json=_inbound(99999, "000000000000000"))
    assert resp.json()["reason"] == "unknown_device"


async def test_webhook_message_free_tier_dropped(client, db_session, fake_fcm_gateway):
    child, _, _, dev = await _setup(db_session, tier="free", watch=True, traccar_id=713)
    resp = await client.post(MESSAGE_WEBHOOK, headers=SECRET_HEADERS, json=_inbound(713, dev.imei))
    assert resp.status_code == 200  # webhook accepts; inbound service drops it
    assert await _count_messages(db_session, child.id) == 0
