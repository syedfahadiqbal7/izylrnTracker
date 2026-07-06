"""child live-location consent + school-day end (Sprint 10, kid trackers)

Revision ID: 0011_child_location_consent
Revises: 0010_school_profile
Create Date: Sprint 10

`student_enrollments.location_opt_in` — a separate, explicit parent consent for the
school to see a child's LIVE location (distinct from parent_opt_in/bus_opt_in), and
`schools.day_ends_at` — the upper bound of the school-hours window in which that live
location is visible. Idempotent; schema.sql declares these too, so a fresh
`alembic upgrade head` no-ops here.
"""
from __future__ import annotations

from alembic import op

revision = "0011_child_location_consent"
down_revision = "0010_school_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE student_enrollments "
        "ADD COLUMN IF NOT EXISTS location_opt_in BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE schools "
        "ADD COLUMN IF NOT EXISTS day_ends_at TIME NOT NULL DEFAULT '16:00'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE schools DROP COLUMN IF EXISTS day_ends_at")
    op.execute("ALTER TABLE student_enrollments DROP COLUMN IF EXISTS location_opt_in")
