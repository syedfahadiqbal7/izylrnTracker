"""audit_log + last_login_at (Sprint 10 Slice 2, B2B observability)

Revision ID: 0009_audit_log
Revises: 0008_bus_trips
Create Date: Sprint 10

`last_login_at` on the three login identities (school_admins, drivers, users) + a
school-scoped `audit_log` for sensitive actions. Idempotent — schema.sql (run by 0001)
declares these too, so a fresh `alembic upgrade head` no-ops here.
"""
from __future__ import annotations

from alembic import op

revision = "0009_audit_log"
down_revision = "0008_bus_trips"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE school_admins ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ")
    op.execute("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            school_id   UUID REFERENCES schools(id) ON DELETE SET NULL,
            actor_type  VARCHAR(20) NOT NULL,
            actor_id    UUID,
            action      VARCHAR(50) NOT NULL,
            entity_type VARCHAR(40),
            entity_id   UUID,
            details     JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_school_time ON audit_log (school_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log (actor_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_login_at")
    op.execute("ALTER TABLE drivers DROP COLUMN IF EXISTS last_login_at")
    op.execute("ALTER TABLE school_admins DROP COLUMN IF EXISTS last_login_at")
