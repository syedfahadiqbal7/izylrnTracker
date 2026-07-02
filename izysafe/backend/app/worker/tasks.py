"""Celery task bodies (Sprint 6 Slice 4).

Celery workers are synchronous, so each task drives its async service via `asyncio.run`.
To avoid binding the app's shared async engine (and its pooled connections) to a throwaway
per-task event loop, each run builds a fresh NullPool engine + session factory and disposes
it afterward — the same isolation principle the test suite uses for its function-scoped
loops. Task logic itself lives in the service classes (unit-tested directly).
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.attendance_service import AttendanceEngine
from app.services.fcm_gateway import FcmGateway
from app.services.maintenance_service import PartitionService, PurgeService
from app.services.subscription_expiry_service import SubscriptionExpiryService
from app.worker.celery_app import celery_app


def _run(job: Callable[[Callable[[], AsyncSession]], Awaitable[Any]]) -> Any:
    """Run an async job with a fresh, disposable engine bound to this task's event loop."""
    async def _main() -> Any:
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            return await job(factory)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


@celery_app.task(name="izysafe.subscriptions.expiry_sweep")
def expiry_sweep() -> int:
    return _run(lambda factory: SubscriptionExpiryService(factory, FcmGateway()).run())


@celery_app.task(name="izysafe.maintenance.partition_rollforward")
def partition_rollforward() -> list[str]:
    return _run(lambda factory: PartitionService(factory).run())


@celery_app.task(name="izysafe.maintenance.soft_delete_purge")
def soft_delete_purge() -> dict[str, int]:
    return _run(lambda factory: PurgeService(factory).run())


@celery_app.task(name="izysafe.attendance.absent_sweep")
def attendance_absent_sweep() -> int:
    return _run(lambda factory: AttendanceEngine(factory).sweep_absent())
