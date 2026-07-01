"""add devices.watch_removed_enabled flag (Sprint 7, F18)

Revision ID: 0003_watch_removed_enabled
Revises: 0002_geofence_active_days
Create Date: Sprint 7

Watch Removed detection (F18) is opt-in per device. The removal *threshold* already
exists (`watch_removed_threshold_min` 5/10/15); this adds the on/off switch. Defaults
to FALSE so the alert never fires until a parent enables it. `watch_removed` is
already a valid `alerts.type`, so no CHECK change is needed.
"""
from __future__ import annotations

from alembic import op

revision = "0003_watch_removed_enabled"
down_revision = "0002_geofence_active_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE devices ADD COLUMN watch_removed_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE devices DROP COLUMN watch_removed_enabled")
