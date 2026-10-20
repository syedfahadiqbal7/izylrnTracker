"""Pydantic schemas for admin-managed app-wide config (migration 0026).

First setting: the OTP delivery channel order — an ordered, enabled-set fallback
list (e.g. ["whatsapp", "sms", "email"]). ``OtpService._deliver`` tries each in
order and uses the first that delivers, so the historical WhatsApp -> SMS
behaviour is just the default list. Structural validation (allowed values, no
dupes, non-empty) is Pydantic's job (422); the service owns semantics.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# The channels an admin may enable, in any order. Keep in sync with
# AppConfigService.OTP_CHANNELS and the otp_sessions.channel CHECK (migration 0026).
OtpChannel = Literal["whatsapp", "sms", "email"]


class OtpChannelsResponse(BaseModel):
    """The configured ordered OTP delivery fallback list."""

    channels: list[OtpChannel]


class OtpChannelsUpdateRequest(BaseModel):
    """Replace the ordered OTP delivery fallback list. At least one channel; no
    duplicates (order is the fallback priority)."""

    channels: list[OtpChannel] = Field(..., min_length=1, max_length=3)

    @field_validator("channels")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("duplicate channels")
        return v


# --------------------------------------------------------------------------- #
# Per-channel provider credentials (admin-managed, migration 0026 app_config)
# --------------------------------------------------------------------------- #
# Update semantics: every field is Optional and merged with `exclude_unset=True`,
# so the admin panel sends only the fields it wants to change. A secret field that
# is left blank is simply omitted → the stored value is kept (never overwritten
# with an empty string). Secrets are masked on read (see AppConfigService), so the
# GET responses below never echo a raw key back to the panel.
class WhatsAppProviderUpdate(BaseModel):
    """MSG91 WhatsApp credentials. `auth_key` is the secret."""

    auth_key: str | None = Field(None, max_length=255)
    template: str | None = Field(None, max_length=120)
    integrated_number: str | None = Field(None, max_length=20)


class SmsProviderUpdate(BaseModel):
    """Twilio SMS credentials. `auth_token` is the secret."""

    account_sid: str | None = Field(None, max_length=255)
    auth_token: str | None = Field(None, max_length=255)
    from_number: str | None = Field(None, max_length=20)


class EmailProviderUpdate(BaseModel):
    """SMTP email credentials. `password` is the secret."""

    host: str | None = Field(None, max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    user: str | None = Field(None, max_length=255)
    password: str | None = Field(None, max_length=255)
    from_address: str | None = Field(None, max_length=255)
    use_tls: bool | None = None


class OtpTestRequest(BaseModel):
    """Send a one-off test OTP through a single channel to verify its credentials."""

    recipient: str = Field(..., min_length=3, max_length=255)
