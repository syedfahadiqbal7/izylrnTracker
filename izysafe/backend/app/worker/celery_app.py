"""Celery app + beat schedule for scheduled jobs (Sprint 6 Slice 4).

Mechanism per CLAUDE.md §4: scheduled/heavy/cross-cutting work runs on Celery + a Redis
broker (the in-request checks stay on FastAPI BackgroundTasks; the batch writer stays a
lifespan loop). The broker/backend default to `redis_url` when the dedicated Celery URLs
are unset. Task bodies live in `app.worker.tasks`.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

_broker = settings.celery_broker_url or settings.redis_url
_backend = settings.celery_result_backend or settings.redis_url

celery_app = Celery("izysafe", broker=_broker, backend=_backend, include=["app.worker.tasks"])

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=600,          # 10 min hard limit per job
    timezone="UTC",
    beat_schedule={
        "subscription-expiry-sweep": {
            "task": "izysafe.subscriptions.expiry_sweep",
            "schedule": crontab(hour=2, minute=0),          # daily 02:00 UTC
        },
        "partition-roll-forward": {
            "task": "izysafe.maintenance.partition_rollforward",
            "schedule": crontab(day_of_month=1, hour=0, minute=30),  # monthly, 1st 00:30 UTC
        },
        "soft-delete-purge": {
            "task": "izysafe.maintenance.soft_delete_purge",
            "schedule": crontab(hour=3, minute=0),          # daily 03:00 UTC
        },
        "attendance-absent-sweep": {
            "task": "izysafe.attendance.absent_sweep",
            # Hourly: late_until varies per school/timezone, so each school is swept on
            # the first run after its window closes. Idempotent (per-school tz + upsert).
            "schedule": crontab(minute=5),
        },
    },
)
