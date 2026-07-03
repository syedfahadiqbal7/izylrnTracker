"""school profile fields — address + contact (Sprint 10, Admin Panel Settings)

Revision ID: 0010_school_profile
Revises: 0009_audit_log
Create Date: Sprint 10

Adds optional `address`, `contact_phone`, `contact_email` to `schools` so the
School Admin Web Panel can manage a full school profile. Idempotent — schema.sql
(run by 0001) declares these too, so a fresh `alembic upgrade head` no-ops here.
"""
from __future__ import annotations

from alembic import op

revision = "0010_school_profile"
down_revision = "0009_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE schools ADD COLUMN IF NOT EXISTS address VARCHAR(300)")
    op.execute("ALTER TABLE schools ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(20)")
    op.execute("ALTER TABLE schools ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE schools DROP COLUMN IF EXISTS contact_email")
    op.execute("ALTER TABLE schools DROP COLUMN IF EXISTS contact_phone")
    op.execute("ALTER TABLE schools DROP COLUMN IF EXISTS address")
