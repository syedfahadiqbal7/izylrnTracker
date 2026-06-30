"""Pydantic schemas for Emergency Contacts (Sprint 4 Slice 3).

The API field is `relationship` (matches the DB column / blueprint); the ORM attribute
is `relationship_label` (``relationship`` is reserved by SQLAlchemy). Aliases bridge
the two so the dict from `model_dump()` lines up with the model attribute.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EmergencyContactCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=100)
    phone: str
    relationship_label: str | None = Field(None, validation_alias="relationship", max_length=30)


class EmergencyContactUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(None, min_length=1, max_length=100)
    phone: str | None = None
    relationship_label: str | None = Field(None, validation_alias="relationship", max_length=30)


class EmergencyContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    child_id: uuid.UUID
    name: str
    phone: str
    relationship_label: str | None = Field(None, serialization_alias="relationship")
    is_app_user: bool
    created_at: datetime
