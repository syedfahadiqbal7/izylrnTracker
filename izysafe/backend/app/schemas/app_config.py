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
