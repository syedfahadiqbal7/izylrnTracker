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

from app.core.config import settings
from app.core.errors import APIException
from app.models.integration import AppConfig

OTP_CHANNELS_KEY = "otp_channels"
# Allowed delivery channels (keep in sync with the otp_sessions.channel CHECK and
# schemas.app_config.OtpChannel). Order here is not significant — the stored list is.
ALLOWED_OTP_CHANNELS: tuple[str, ...] = ("whatsapp", "sms", "email")
# Default = today's behaviour (WhatsApp primary, SMS fallback).
DEFAULT_OTP_CHANNELS: list[str] = ["whatsapp", "sms"]

# Per-channel provider credentials live in app_config too (one row per channel).
# Only fields the admin actually set are stored; everything else resolves from the
# environment (panel overrides env, env is the fallback). Secret fields are masked on
# read — the GET never echoes a raw key back to the panel.
OTP_PROVIDER_KEYS: dict[str, str] = {
    "whatsapp": "otp_provider_whatsapp",
    "sms": "otp_provider_sms",
    "email": "otp_provider_email",
}
PROVIDER_SECRET_FIELDS: dict[str, set[str]] = {
    "whatsapp": {"auth_key"},
    "sms": {"auth_token"},
    "email": {"password"},
}


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

    # ------------------------------------------------------ provider credentials
    def _env_providers(self) -> dict[str, dict]:
        """The environment-configured credentials — the fallback layer."""
        return {
            "whatsapp": {
                "auth_key": settings.msg91_auth_key,
                "template": settings.msg91_whatsapp_template,
                "integrated_number": settings.twilio_from_number,
            },
            "sms": {
                "account_sid": settings.twilio_sid,
                "auth_token": settings.twilio_token,
                "from_number": settings.twilio_from_number,
            },
            "email": {
                "host": settings.smtp_host,
                "port": settings.smtp_port,
                "user": settings.smtp_user,
                "password": settings.smtp_password,
                "from_address": settings.smtp_from,
                "use_tls": settings.smtp_use_tls,
            },
        }

    async def _raw_provider(self, channel: str) -> dict:
        row = await self.db.get(AppConfig, OTP_PROVIDER_KEYS[channel])
        return row.value if row and isinstance(row.value, dict) else {}

    @staticmethod
    def _pick(db_cfg: dict, field: str, env_val):
        """Panel value wins when set (non-empty); else the environment value."""
        if field in db_cfg and db_cfg[field] not in (None, ""):
            return db_cfg[field]
        return env_val

    async def resolve_otp_providers(self) -> dict[str, dict]:
        """Effective credentials per channel — DB values merged over env, field by
        field. This is what the gateways actually send with."""
        env = self._env_providers()
        out: dict[str, dict] = {}
        for channel, fields in env.items():
            db_cfg = await self._raw_provider(channel)
            out[channel] = {f: self._pick(db_cfg, f, v) for f, v in fields.items()}
        return out

    async def get_otp_providers_masked(self) -> dict[str, dict]:
        """The effective config for the admin panel, with secrets masked: each secret
        field becomes a ``<field>_set`` boolean (true when a value exists from DB or
        env), so a raw key is never returned."""
        resolved = await self.resolve_otp_providers()
        out: dict[str, dict] = {}
        for channel, cfg in resolved.items():
            secrets = PROVIDER_SECRET_FIELDS[channel]
            masked: dict = {}
            for field, val in cfg.items():
                if field in secrets:
                    masked[f"{field}_set"] = bool(val)
                else:
                    masked[field] = val
            out[channel] = masked
        return out

    async def set_otp_provider(self, channel: str, updates: dict) -> dict[str, dict]:
        """Merge the provided fields into the channel's stored config (fields not
        provided are left untouched → a blank secret keeps the stored one). Returns
        the full masked provider view."""
        if channel not in OTP_PROVIDER_KEYS:
            raise APIException(404, "UNKNOWN_CHANNEL", "Unknown OTP channel")
        existing = await self._raw_provider(channel)
        merged = {**existing, **updates}
        stmt = (
            pg_insert(AppConfig)
            .values(key=OTP_PROVIDER_KEYS[channel], value=merged)
            .on_conflict_do_update(
                index_elements=[AppConfig.key],
                set_={"value": merged, "updated_at": func.now()},
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return await self.get_otp_providers_masked()
