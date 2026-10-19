"""Add parent contact-profile fields to users: address + map pin + extra numbers.

Idempotent ALTERs (ADD COLUMN IF NOT EXISTS) layered on top of schema.sql.
"""
from __future__ import annotations

from alembic import op

revision = "0022_user_profile_fields"
down_revision = "0021_parents_menu_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS address TEXT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS home_lat DOUBLE PRECISION")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS home_lng DOUBLE PRECISION")
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS additional_contacts "
        "JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS additional_contacts")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS home_lng")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS home_lat")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS address")
