"""Pydantic schemas for audio features (Sprint 5): Sound Around (F11)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AudioSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    device_id: uuid.UUID | None
    user_id: uuid.UUID
    started_at: datetime
    duration_s: int | None
