"""Pydantic schema for the Alerts inbox API (Sprint 4 Slice 4)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID | None = None
    type: str
    title: str | None = None
    body: str | None = None
    data: dict | None = None
    read: bool
    created_at: datetime
