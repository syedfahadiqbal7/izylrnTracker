"""Tests for the 5s batch writer (Sprint 2, Slice 2).

Covers: drain + bulk insert, empty buffer, max_batch cap, poison-row drop,
transient-failure re-queue, and the shutdown final-flush guarantee.

`locations` has no FKs (CLAUDE.md §3.3 denormalized, hot, batch-inserted), so
tests use arbitrary device/child UUIDs without seeding rows.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.redis_keys import BATCH_LOCATIONS
from app.models.location import Location
from app.services.batch_writer import BatchWriter


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _SessionCtx:
    """Async context manager yielding the shared test session without closing it
    (so the outer savepoint/rollback isolation in conftest stays intact)."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc) -> bool:
        return False


def _make_writer(redis_client, db_session, **kw) -> BatchWriter:
    return BatchWriter(redis_client, session_factory=lambda: _SessionCtx(db_session), **kw)


def _row(*, device_id=None, child_id=None, lat=25.2048, lng=55.2708,
         speed=18.5, battery=80, ts=None) -> str:
    ts = ts or datetime.now(timezone.utc)
    return json.dumps({
        "device_id": str(device_id or uuid.uuid4()),
        "child_id": str(child_id or uuid.uuid4()),
        "lat": lat, "lng": lng, "accuracy": 8.0, "speed": speed,
        "altitude": 12.0, "bearing": 90.0, "battery": battery,
        "is_moving": True, "address": None, "timestamp": ts.isoformat(),
    })


async def _count_for(db, child_id) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(Location).where(Location.child_id == child_id)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
async def test_flush_inserts_all_rows_and_empties_buffer(redis_client, db_session):
    child_id = uuid.uuid4()
    for _ in range(3):
        await redis_client.lpush(BATCH_LOCATIONS, _row(child_id=child_id))

    writer = _make_writer(redis_client, db_session)
    written = await writer.flush_once()

    assert written == 3
    assert await redis_client.llen(BATCH_LOCATIONS) == 0
    assert await _count_for(db_session, child_id) == 3


async def test_inserted_values_are_correct(redis_client, db_session):
    child_id, device_id = uuid.uuid4(), uuid.uuid4()
    ts = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
    await redis_client.lpush(
        BATCH_LOCATIONS,
        _row(device_id=device_id, child_id=child_id, lat=25.5, lng=55.6, speed=22.2, battery=73, ts=ts),
    )
    await _make_writer(redis_client, db_session).flush_once()

    row = (
        await db_session.execute(select(Location).where(Location.child_id == child_id))
    ).scalar_one()
    assert row.device_id == device_id
    assert row.lat == 25.5 and row.lng == 55.6
    assert row.speed == 22.2
    assert row.battery == 73
    assert row.is_moving is True
    assert row.timestamp == ts


async def test_empty_buffer_is_noop(redis_client, db_session):
    assert await _make_writer(redis_client, db_session).flush_once() == 0


# --------------------------------------------------------------------------- #
# Capping + robustness
# --------------------------------------------------------------------------- #
async def test_max_batch_caps_each_flush(redis_client, db_session):
    child_id = uuid.uuid4()
    for _ in range(5):
        await redis_client.lpush(BATCH_LOCATIONS, _row(child_id=child_id))

    writer = _make_writer(redis_client, db_session, max_batch=2)
    assert await writer.flush_once() == 2
    assert await redis_client.llen(BATCH_LOCATIONS) == 3  # remainder waits for next tick


async def test_poison_row_dropped_not_requeued(redis_client, db_session):
    child_id = uuid.uuid4()
    await redis_client.lpush(BATCH_LOCATIONS, "this is not json")
    await redis_client.lpush(BATCH_LOCATIONS, _row(child_id=child_id))

    written = await _make_writer(redis_client, db_session).flush_once()

    assert written == 1                                   # valid row inserted
    assert await redis_client.llen(BATCH_LOCATIONS) == 0  # poison dropped, not requeued
    assert await _count_for(db_session, child_id) == 1


async def test_db_failure_requeues_rows(redis_client, db_session):
    child_id = uuid.uuid4()
    for _ in range(2):
        await redis_client.lpush(BATCH_LOCATIONS, _row(child_id=child_id))

    writer = _make_writer(redis_client, db_session)

    async def _boom(rows):
        raise RuntimeError("db down")

    writer._bulk_insert = _boom  # simulate a transient Postgres failure

    written = await writer.flush_once()
    assert written == 0
    assert await redis_client.llen(BATCH_LOCATIONS) == 2   # rows re-queued, nothing lost
    assert await _count_for(db_session, child_id) == 0


# --------------------------------------------------------------------------- #
# Shutdown flush
# --------------------------------------------------------------------------- #
async def test_shutdown_flushes_remaining_rows(redis_client, db_session):
    child_id = uuid.uuid4()
    for _ in range(4):
        await redis_client.lpush(BATCH_LOCATIONS, _row(child_id=child_id))

    # Long interval: rows should be drained by the final flush on stop(), not a tick.
    writer = _make_writer(redis_client, db_session, interval=60)
    writer.start()
    await writer.stop()

    assert await redis_client.llen(BATCH_LOCATIONS) == 0
    assert await _count_for(db_session, child_id) == 4
    assert writer._task is None
