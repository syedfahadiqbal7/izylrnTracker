"""driver login: drivers.password_hash + unique phone (Sprint 10, F28 driver app)

Revision ID: 0007_driver_login
Revises: 0006_bus_device_owner
Create Date: Sprint 10

School-issued driver login (Decision D-A): the admin sets an access code, stored here
as a bcrypt hash (null ⇒ the driver can't log in yet). Phone is the login key, so it's
uniquely indexed among non-null values. Idempotent — schema.sql (run by 0001) already
declares both, so a fresh `alembic upgrade head` no-ops here.
"""
from __future__ import annotations

from alembic import op

revision = "0007_driver_login"
down_revision = "0006_bus_device_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS password_hash VARCHAR(100)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_drivers_phone ON drivers (phone) WHERE phone IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_drivers_phone")
    op.execute("ALTER TABLE drivers DROP COLUMN IF EXISTS password_hash")
