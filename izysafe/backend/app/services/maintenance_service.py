"""Scheduled maintenance jobs (Sprint 6 Slice 4) — Celery-beat driven.

* `PartitionService` — monthly roll-forward of the `locations` monthly partitions. Calls
  the idempotent `create_locations_partition(year, month)` DB function (CLAUDE.md §3.5) for
  the next `partition_lookahead_months` so ingestion never hits a missing partition.
* `PurgeService` — hard-deletes `users`/`children`/`devices` soft-deleted more than
  `soft_delete_retention_days` ago (the 30-day purge deferred from Sprint 4). FK cascades
  clean up dependents; each table is swept independently since a device can be soft-deleted
  without its child.

Both run in a Celery worker via a `session_factory` (own session, like the other jobs).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.child import Child
from app.models.device import Device
from app.models.user import User

logger = logging.getLogger("izysafe.jobs.maintenance")


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    """(year, month) advanced by n months (1-based month)."""
    index = (year * 12 + (month - 1)) + n
    return index // 12, index % 12 + 1


class PartitionService:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self.session_factory = session_factory

    async def run(self, now: datetime | None = None) -> list[str]:
        """Ensure the next N months of locations partitions exist. Idempotent — the DB
        function no-ops when a partition is already present. Returns the (year, month)
        pairs ensured, for logging/tests."""
        now = now or datetime.now(UTC)
        ensured: list[str] = []
        async with self.session_factory() as session:
            for i in range(settings.partition_lookahead_months + 1):
                year, month = _add_months(now.year, now.month, i)
                await session.execute(
                    text("SELECT create_locations_partition(:y, :m)"),
                    {"y": year, "m": month},
                )
                ensured.append(f"{year}_{month:02d}")
            await session.commit()
        logger.info("Partition roll-forward ensured: %s", ", ".join(ensured))
        return ensured


class PurgeService:
    # Tables carrying soft-delete (deleted_at); FK cascades handle their dependents.
    _MODELS = (Device, Child, User)

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self.session_factory = session_factory

    async def run(self, now: datetime | None = None) -> dict[str, int]:
        """Hard-delete rows soft-deleted before the retention cutoff. Returns per-table
        deleted counts."""
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(days=settings.soft_delete_retention_days)
        counts: dict[str, int] = {}
        async with self.session_factory() as session:
            for model in self._MODELS:
                stale = (
                    await session.execute(
                        select(func.count())
                        .select_from(model)
                        .where(model.deleted_at.is_not(None), model.deleted_at < cutoff)
                    )
                ).scalar_one()
                if stale:
                    await session.execute(
                        delete(model).where(
                            model.deleted_at.is_not(None), model.deleted_at < cutoff
                        )
                    )
                counts[model.__tablename__] = stale
            await session.commit()
        if any(counts.values()):
            logger.info("Soft-delete purge removed: %s", counts)
        return counts
