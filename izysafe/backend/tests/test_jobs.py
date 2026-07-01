"""Tests for the Sprint 6 Slice 4 scheduled jobs (service logic, invoked directly).

Like the other background-task services, these take a session_factory; the tests bind it
to the isolated test session via NonClosingSession (savepoint/rollback), so partition DDL
and hard deletes are rolled back after each test.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from app.models.alert import Alert
from app.models.child import Child
from app.models.device import Device
from app.models.user import Subscription, User
from app.services.maintenance_service import PurgeService
from app.services.subscription_expiry_service import SubscriptionExpiryService
from tests.conftest import NonClosingSession


def _factory(db_session):
    return lambda: NonClosingSession(db_session)


async def _user(db, *, tier="premium", expires=None, deleted_at=None):
    u = User(
        phone="+9198" + uuid.uuid4().hex[:8], country_code="+91",
        subscription_tier=tier, subscription_expires_at=expires, deleted_at=deleted_at,
    )
    db.add(u)
    await db.flush()
    return u


# --------------------------------------------------------------------------- #
# Subscription expiry sweep
# --------------------------------------------------------------------------- #
async def test_expiry_downgrades_lapsed_user(db_session, fake_fcm_gateway):
    past = datetime.now(UTC) - timedelta(days=1)
    user = await _user(db_session, tier="premium", expires=past)
    db_session.add(Subscription(
        user_id=user.id, tier="premium", gateway="razorpay", status="active", expires_at=past,
    ))
    await db_session.flush()

    n = await SubscriptionExpiryService(_factory(db_session), fake_fcm_gateway).run()
    assert n == 1

    refreshed = await db_session.get(User, user.id)
    assert refreshed.subscription_tier == "free"
    row = (await db_session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )).scalar_one()
    assert row.status == "expired"
    # User was notified.
    alerts = (await db_session.execute(
        select(Alert).where(Alert.user_id == user.id, Alert.type == "system")
    )).scalars().all()
    assert len(alerts) == 1


async def test_expiry_leaves_active_user(db_session, fake_fcm_gateway):
    future = datetime.now(UTC) + timedelta(days=10)
    user = await _user(db_session, tier="premium", expires=future)
    n = await SubscriptionExpiryService(_factory(db_session), fake_fcm_gateway).run()
    assert n == 0
    refreshed = await db_session.get(User, user.id)
    assert refreshed.subscription_tier == "premium"


async def test_expiry_ignores_free_user(db_session, fake_fcm_gateway):
    await _user(db_session, tier="free", expires=None)
    n = await SubscriptionExpiryService(_factory(db_session), fake_fcm_gateway).run()
    assert n == 0


# --------------------------------------------------------------------------- #
# Soft-delete purge
# --------------------------------------------------------------------------- #
async def test_purge_removes_old_soft_deleted_user(db_session):
    old = datetime.now(UTC) - timedelta(days=31)
    user = await _user(db_session, tier="free", deleted_at=old)
    uid = user.id

    counts = await PurgeService(_factory(db_session)).run()
    assert counts["users"] == 1
    assert (await db_session.get(User, uid)) is None


async def test_purge_keeps_recent_soft_deleted(db_session):
    recent = datetime.now(UTC) - timedelta(days=5)
    user = await _user(db_session, tier="free", deleted_at=recent)
    counts = await PurgeService(_factory(db_session)).run()
    assert counts["users"] == 0
    assert (await db_session.get(User, user.id)) is not None


async def test_purge_keeps_live_rows(db_session):
    user = await _user(db_session, tier="free", deleted_at=None)
    counts = await PurgeService(_factory(db_session)).run()
    assert counts["users"] == 0
    assert (await db_session.get(User, user.id)) is not None


async def test_purge_removes_stale_child_and_device(db_session):
    old = datetime.now(UTC) - timedelta(days=40)
    child = Child(name="Old", deleted_at=old)
    db_session.add(child)
    await db_session.flush()
    device = Device(
        child_id=child.id, name="Old Watch", device_type="watch",
        imei=uuid.uuid4().hex[:15], deleted_at=old,
    )
    db_session.add(device)
    await db_session.flush()

    counts = await PurgeService(_factory(db_session)).run()
    assert counts["devices"] == 1
    assert counts["children"] == 1
    assert (await db_session.get(Child, child.id)) is None


# --------------------------------------------------------------------------- #
# Partition roll-forward
# --------------------------------------------------------------------------- #
async def test_partition_rollforward_creates_future_partitions(db_session, monkeypatch):
    from app.services import maintenance_service

    monkeypatch.setattr(maintenance_service.settings, "partition_lookahead_months", 2)
    # A far-future month the bootstrap didn't create, so the DB function actually builds it.
    far = datetime(2035, 3, 1, tzinfo=UTC)
    ensured = await maintenance_service.PartitionService(_factory(db_session)).run(now=far)
    assert ensured == ["2035_03", "2035_04", "2035_05"]

    exists = (await db_session.execute(
        text("SELECT to_regclass('locations_2035_03')")
    )).scalar_one()
    assert exists is not None


async def test_partition_rollforward_idempotent(db_session):
    from app.services import maintenance_service

    far = datetime(2036, 6, 1, tzinfo=UTC)
    svc = maintenance_service.PartitionService(_factory(db_session))
    first = await svc.run(now=far)
    second = await svc.run(now=far)  # no error on the second pass — function no-ops
    assert first == second
