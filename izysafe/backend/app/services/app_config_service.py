"""App-wide, admin-managed config service (migration 0026).

Mirrors I18nService: thin CRUD over a key/value table, committing inside each
method. The only setting today is the OTP delivery channel order — an ordered,
enabled-set fallback list consumed by ``OtpService._deliver`` (tries each channel
in order, uses the first that delivers). The default list reproduces the historic
WhatsApp -> SMS behaviour, and is returned whenever the row is missing or empty so
OTP delivery never breaks on a config gap.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIException
from app.models.integration import AppConfig

OTP_CHANNELS_KEY = "otp_channels"
# Allowed delivery channels (keep in sync with the otp_sessions.channel CHECK and
# schemas.app_config.OtpChannel). Order here is not significant — the stored list is.
ALLOWED_OTP_CHANNELS: tuple[str, ...] = ("whatsapp", "sms", "email")
# Default = today's behaviour (WhatsApp primary, SMS fallback).
DEFAULT_OTP_CHANNELS: list[str] = ["whatsapp", "sms"]


class AppConfigService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_otp_channels(self) -> list[str]:
        """The ordered OTP delivery fallback list. Falls back to the default when
        unset/empty, and drops any unknown channel defensively (so a stale config
        can never direct delivery at a channel the code no longer handles)."""
        row = await self.db.get(AppConfig, OTP_CHANNELS_KEY)
        raw = row.value.get("channels") if row and isinstance(row.value, dict) else None
        if not isinstance(raw, list):
            return list(DEFAULT_OTP_CHANNELS)
        channels = [c for c in raw if c in ALLOWED_OTP_CHANNELS]
        return channels or list(DEFAULT_OTP_CHANNELS)

    async def set_otp_channels(self, channels: list[str]) -> list[str]:
        """Replace the channel order (idempotent upsert). Structural validation
        (allowed values, no dupes, non-empty) is done by the Pydantic request; this
        is the semantic backstop."""
        cleaned = [c for c in channels if c in ALLOWED_OTP_CHANNELS]
        if not cleaned:
            raise APIException(
                422, "INVALID_OTP_CHANNELS", "At least one valid OTP channel is required"
            )
        value = {"channels": cleaned}
        stmt = (
            pg_insert(AppConfig)
            .values(key=OTP_CHANNELS_KEY, value=value)
            .on_conflict_do_update(
                index_elements=[AppConfig.key],
                set_={"value": value, "updated_at": func.now()},
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return cleaned
