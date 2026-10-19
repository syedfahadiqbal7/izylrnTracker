"""Configurable OTP delivery channel (app-wide, admin-managed).

Adds a generic ``app_config`` key/value (JSONB) table — mirroring the i18n/menu
precedent of admin-managed, app-wide config — and seeds the ``otp_channels`` row
with today's behaviour (WhatsApp -> SMS fallback) so delivery is unchanged until
an admin edits it. Also relaxes the ``otp_sessions.channel`` CHECK to allow
``'email'`` (Email is now a selectable OTP channel).

Idempotent (migration 0001 runs schema.sql verbatim, later migrations ALTER on
top): CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING (the seed
never clobbers an admin edit on re-run), and the CHECK is dropped-if-exists then
re-added.
"""
from __future__ import annotations

from alembic import op

revision = "0026_otp_channel_config"
down_revision = "0025_consent_wizard_i18n"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app_config (
            key        VARCHAR(60) PRIMARY KEY,
            value      JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Seed the OTP channel order with today's behaviour (WhatsApp -> SMS). ON
    # CONFLICT DO NOTHING so re-running never overwrites an admin's later edit.
    op.execute(
        """
        INSERT INTO app_config (key, value)
        VALUES ('otp_channels', '{"channels": ["whatsapp", "sms"]}'::jsonb)
        ON CONFLICT (key) DO NOTHING
        """
    )
    # Email is now a selectable OTP channel — relax the delivered-channel CHECK.
    # schema.sql's inline CHECK is auto-named `otp_sessions_channel_check`; drop that
    # (and any prior ck_otp_channel) before adding the model-named one. Idempotent.
    op.execute("ALTER TABLE otp_sessions DROP CONSTRAINT IF EXISTS otp_sessions_channel_check")
    op.execute("ALTER TABLE otp_sessions DROP CONSTRAINT IF EXISTS ck_otp_channel")
    op.execute(
        "ALTER TABLE otp_sessions ADD CONSTRAINT ck_otp_channel "
        "CHECK (channel IN ('whatsapp', 'sms', 'email'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE otp_sessions DROP CONSTRAINT IF EXISTS ck_otp_channel")
    op.execute("ALTER TABLE otp_sessions DROP CONSTRAINT IF EXISTS otp_sessions_channel_check")
    op.execute(
        "ALTER TABLE otp_sessions ADD CONSTRAINT otp_sessions_channel_check "
        "CHECK (channel IN ('whatsapp', 'sms'))"
    )
    op.execute("DROP TABLE IF EXISTS app_config")
