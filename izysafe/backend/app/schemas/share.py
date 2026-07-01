"""Pydantic schemas for Share Links (Sprint 7 Slice 3, F22).

A share link is a public, login-less live-tracking URL. Creation is Basic+ (gated in
the service). The owner-facing response carries management fields (token, url,
expiry, view count); the PUBLIC response is deliberately minimal (Decision D10) —
the child's first name + the latest fix only, never history/battery/device.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings

# The only validity durations we hand out (Decision D9); 24 h is the hard ceiling.
ALLOWED_TTL_HOURS = (1, 8, 24)


class ShareLinkCreate(BaseModel):
    ttl_hours: int = Field(default_factory=lambda: settings.share_link_default_ttl_hours)

    @field_validator("ttl_hours")
    @classmethod
    def _ttl(cls, v: int) -> int:
        if v not in ALLOWED_TTL_HOURS:
            raise ValueError(f"ttl_hours must be one of {ALLOWED_TTL_HOURS}")
        return v


class ShareLinkResponse(BaseModel):
    """Owner-facing view (create + list) — includes the token/url for sharing."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    token: str
    url: str
    expires_at: datetime
    view_count: int
    revoked: bool
    created_at: datetime


class LatestLocation(BaseModel):
    lat: float
    lng: float
    timestamp: datetime | None = None


class PublicShareResponse(BaseModel):
    """Public view (GET /share/{token}) — name + live location only (Decision D10)."""

    child_name: str
    location: LatestLocation | None = None
    expires_at: datetime
