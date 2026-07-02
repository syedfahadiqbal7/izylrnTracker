"""attendance links: geofences.school_id + schools.school_days (Sprint 8, F27)

Revision ID: 0004_attendance_links
Revises: 0003_watch_removed_enabled
Create Date: Sprint 8

Attendance is derived from a child's school-zone geofence transitions (Decision D9),
so a geofence can be tagged with the `school_id` it is the attendance anchor for
(ON DELETE SET NULL — the parent still owns the zone). `schools.school_days` lets the
daily absent sweep skip non-school weekdays (default Mon–Fri) in addition to
`schools.holidays`.
"""
from __future__ import annotations

from alembic import op

revision = "0004_attendance_links"
down_revision = "0003_watch_removed_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `schema.sql` (run by 0001) already declares the bare `geofences.school_id` column
    # and `schools.school_days`, so ADD COLUMN is IF NOT EXISTS (fresh migrate no-ops).
    # The FK is added here (not in schema.sql) because `schools` is defined AFTER
    # `geofences` there — an inline reference would be a forward reference.
    op.execute("ALTER TABLE geofences ADD COLUMN IF NOT EXISTS school_id UUID")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_geofences_school'
            ) THEN
                ALTER TABLE geofences ADD CONSTRAINT fk_geofences_school
                    FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_geofences_school_id "
        "ON geofences (school_id) WHERE school_id IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE schools ADD COLUMN IF NOT EXISTS school_days "
        "INTEGER[] NOT NULL DEFAULT ARRAY[1,2,3,4,5]"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE schools DROP COLUMN IF EXISTS school_days")
    op.execute("DROP INDEX IF EXISTS idx_geofences_school_id")
    op.execute("ALTER TABLE geofences DROP CONSTRAINT IF EXISTS fk_geofences_school")
    op.execute("ALTER TABLE geofences DROP COLUMN IF EXISTS school_id")
