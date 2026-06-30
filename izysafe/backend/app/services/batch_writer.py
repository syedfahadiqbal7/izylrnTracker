"""5-second batch writer — the single long-lived loop of Flow A (CLAUDE.md §4).

The webhook hot path only LPUSHes rows onto `batch:locations`; this lifespan task
drains them every 5s and bulk-INSERTs into the partitioned `locations` table, so
the high-volume time-series write never sits on the request path.

Reliability:
  * Drain is FIFO and capped (RPOP count ≤ max_batch) so one tick can't OOM.
  * Transient DB failure → rows are re-queued (RPUSH back to the tail) and retried
    next tick; nothing is lost on a brief Postgres blip.
  * Un-parseable rows are dropped (logged) so a single poison entry can't wedge
    the loop forever.
  * A `finally` flush guarantees a final drain on shutdown, even if the task is
    stopped before its first tick.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.redis_keys import BATCH_LOCATIONS
from app.models.location import Location

logger = logging.getLogger("izysafe.batch")

DEFAULT_INTERVAL = 5.0
DEFAULT_MAX_BATCH = 1000

_COLUMNS = (
    "device_id", "child_id", "lat", "lng", "accuracy", "speed",
    "altitude", "bearing", "battery", "is_moving", "address", "timestamp",
)


def _to_row(d: dict[str, Any]) -> dict[str, Any]:
    """Map a buffered JSON dict → a `locations` insert row with proper types."""
    return {
        "device_id": uuid.UUID(d["device_id"]),
        "child_id": uuid.UUID(d["child_id"]),
        "lat": d["lat"],
        "lng": d["lng"],
        "accuracy": d.get("accuracy"),
        "speed": d.get("speed"),
        "altitude": d.get("altitude"),
        "bearing": d.get("bearing"),
        "battery": d.get("battery"),
        "is_moving": d.get("is_moving"),
        "address": d.get("address"),
        "timestamp": datetime.fromisoformat(d["timestamp"]),
    }


class BatchWriter:
    def __init__(
        self,
        redis: Redis,
        session_factory: Callable[[], AsyncSession] = AsyncSessionLocal,
        interval: float = DEFAULT_INTERVAL,
        max_batch: int = DEFAULT_MAX_BATCH,
    ) -> None:
        self.redis = redis
        self.session_factory = session_factory
        self.interval = interval
        self.max_batch = max_batch
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="batch-writer")
        logger.info("Batch writer started (interval=%ss, max_batch=%d).", self.interval, self.max_batch)

    async def stop(self) -> None:
        """Signal shutdown and await the task (which does a final flush)."""
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        logger.info("Batch writer stopped.")

    async def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    # Wake early if stop is signalled; otherwise tick every `interval`.
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                except asyncio.TimeoutError:
                    pass
                await self.flush_once()
        finally:
            # Guarantee a final drain even if stopped before the first tick.
            await self.flush_once()

    # ----------------------------------------------------------------- flush
    async def flush_once(self) -> int:
        """Drain up to `max_batch` rows and bulk-insert them. Returns rows written."""
        try:
            raw = await self._drain()
        except RedisError:
            logger.exception("Batch writer: failed to drain %s", BATCH_LOCATIONS)
            return 0
        if not raw:
            return 0

        rows: list[dict[str, Any]] = []
        for item in raw:
            try:
                rows.append(_to_row(json.loads(item)))
            except (ValueError, KeyError, TypeError):
                # Poison row — drop it (do NOT re-queue) so the loop can't wedge.
                logger.warning("Batch writer: dropping un-parseable row: %r", item)

        if not rows:
            return 0

        try:
            await self._bulk_insert(rows)
        except Exception:
            logger.exception("Batch writer: insert of %d rows failed — re-queueing", len(rows))
            await self._requeue(raw)
            return 0

        logger.debug("Batch writer: inserted %d locations.", len(rows))
        return len(rows)

    async def _drain(self) -> list[str]:
        items = await self.redis.rpop(BATCH_LOCATIONS, self.max_batch)
        if not items:
            return []
        return items if isinstance(items, list) else [items]

    async def _requeue(self, raw: list[str]) -> None:
        try:
            await self.redis.rpush(BATCH_LOCATIONS, *raw)
        except RedisError:
            logger.exception("Batch writer: re-queue failed — %d rows lost", len(raw))

    async def _bulk_insert(self, rows: list[dict[str, Any]]) -> None:
        async with self.session_factory() as session:
            await session.execute(insert(Location), rows)
            await session.commit()
