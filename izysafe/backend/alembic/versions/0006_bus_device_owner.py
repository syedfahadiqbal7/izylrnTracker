"""bus device ownership: nullable child_id + devices.school_id (Sprint 8, F28)

Revision ID: 0006_bus_device_owner
Revises: 0005_bus_device_and_alert
Create Date: Sprint 8

A bus GPS tracker is a `devices` row with NO child. This drops the `child_id` NOT NULL,
adds `devices.school_id` (bus devices belong to a school), and a `ck_device_owner` CHECK
enforcing the split: a bus has school_id + null child_id; every other device has a
child_id + null school_id. Idempotent + FK added here (schools is defined later in
schema.sql) — same pattern as 0004's geofences.school_id.
"""
from __future__ import annotations

from alembic import op

revision = "0006_bus_device_owner"
down_revision = "0005_bus_device_and_alert"
branch_labels = None
depends_on = None

_OWNER_CHECK = (
    "(device_type = 'bus' AND child_id IS NULL AND school_id IS NOT NULL) "
    "OR (device_type <> 'bus' AND child_id IS NOT NULL AND school_id IS NULL)"
)


def upgrade() -> None:
    op.execute("ALTER TABLE devices ALTER COLUMN child_id DROP NOT NULL")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS school_id UUID")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_devices_school') THEN
                ALTER TABLE devices ADD CONSTRAINT fk_devices_school
                    FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_devices_school ON devices (school_id) WHERE school_id IS NOT NULL"
    )
    op.execute("ALTER TABLE devices DROP CONSTRAINT IF EXISTS ck_device_owner")
    op.execute(f"ALTER TABLE devices ADD CONSTRAINT ck_device_owner CHECK ({_OWNER_CHECK})")


def downgrade() -> None:
    op.execute("ALTER TABLE devices DROP CONSTRAINT IF EXISTS ck_device_owner")
    op.execute("DROP INDEX IF EXISTS idx_devices_school")
    op.execute("ALTER TABLE devices DROP CONSTRAINT IF EXISTS fk_devices_school")
    op.execute("ALTER TABLE devices DROP COLUMN IF EXISTS school_id")
    # child_id back to NOT NULL (fails if bus rows exist — delete them before downgrading).
    op.execute("ALTER TABLE devices ALTER COLUMN child_id SET NOT NULL")
