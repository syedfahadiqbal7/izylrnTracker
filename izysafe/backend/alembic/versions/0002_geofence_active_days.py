"""widen geofences.active_days default to all 7 days (Sprint 3)

Revision ID: 0002_geofence_active_days
Revises: 0001_initial_schema
Create Date: Sprint 3

A geofence created without an explicit schedule should alert every day, not just
Mon–Fri. This changes only the column DEFAULT (new rows); existing rows are
unaffected. The child's `school_active_days` stays Mon–Fri (school is weekdays).
"""
from __future__ import annotations

from alembic import op

revision = "0002_geofence_active_days"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE geofences ALTER COLUMN active_days SET DEFAULT ARRAY[1,2,3,4,5,6,7]")


def downgrade() -> None:
    op.execute("ALTER TABLE geofences ALTER COLUMN active_days SET DEFAULT ARRAY[1,2,3,4,5]")
