"""Pydantic schemas for Chat (Sprint 7 Slice 6, F23).

Short two-way text between a parent and the child's watch. Sending is Basic+ (gated in
the service). Content is capped at 120 chars (matches the chat_messages column). The
inbound schema is what the watch → backend forwarder posts to the message webhook.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatSendRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=120)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    sender_type: str          # 'parent' | 'child'
    sender_id: uuid.UUID | None = None
    content: str
    status: str               # 'queued' | 'sent' | 'delivered' | 'failed'
    created_at: datetime


class WatchMessageIn(BaseModel):
    """Inbound watch → backend message (secret-authed message webhook)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    device_id: int | None = Field(default=None, alias="deviceId")
    unique_id: str | None = Field(default=None, alias="uniqueId")  # IMEI fallback
    content: str = Field(..., min_length=1, max_length=120)
