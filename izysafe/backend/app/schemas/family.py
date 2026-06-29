"""Schemas for guardian invites + family management."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

_ROLE = Literal["guardian", "grandparent", "teacher", "relative"]


class InviteCreate(BaseModel):
    phone: str = Field(..., examples=["+919812345678"])
    role: _ROLE = "guardian"
    can_view: bool = True
    can_call: bool = False
    can_manage: bool = False


class InviteResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    phone: str
    role: str
    can_view: bool
    can_call: bool
    can_manage: bool
    expires_at: datetime
    channel: str | None = None     # "whatsapp" | "sms" | None (delivery failed)
    invite_link: str


class AcceptResponse(BaseModel):
    child_id: uuid.UUID
    child_name: str
    role: str
    can_view: bool
    can_call: bool
    can_manage: bool
