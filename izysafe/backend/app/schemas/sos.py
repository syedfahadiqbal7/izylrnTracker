"""Pydantic schemas for the SOS read/resolve API (Sprint 4 Slice 2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SosResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    child_name: str | None = None
    device_id: uuid.UUID | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    approximate: bool
    status: str
    triggered_at: datetime
    resolved_at: datetime | None = None
    resolved_by: uuid.UUID | None = None
