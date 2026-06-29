"""Pydantic schemas for Children CRUD."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SPEED = Literal[20, 30, 40, 60, 80, 100, 120]


def _validate_days(v: list[int] | None) -> list[int] | None:
    if v is None:
        return v
    if not v or any(d < 1 or d > 7 for d in v) or len(set(v)) != len(v):
        raise ValueError("school_active_days must be unique values 1-7 (1=Mon..7=Sun)")
    return v


def _validate_dob(v: date | None) -> date | None:
    if v and v > date.today():
        raise ValueError("dob cannot be in the future")
    return v


class ChildCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    nickname: str | None = Field(None, max_length=50)
    dob: date | None = None
    photo_url: str | None = None
    school_name: str | None = Field(None, max_length=200)
    class_grade: str | None = Field(None, max_length=50)

    _dob = field_validator("dob")(_validate_dob)


class ChildUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    nickname: str | None = Field(None, max_length=50)
    dob: date | None = None
    photo_url: str | None = None
    school_name: str | None = Field(None, max_length=200)
    class_grade: str | None = Field(None, max_length=50)
    # settings
    school_mode_enabled: bool | None = None
    school_hours_from: time | None = None
    school_hours_to: time | None = None
    school_active_days: list[int] | None = None
    speed_alert_enabled: bool | None = None
    speed_threshold_kmh: _SPEED | None = None
    teen_mode_enabled: bool | None = None

    _dob = field_validator("dob")(_validate_dob)
    _days = field_validator("school_active_days")(_validate_days)


class ChildPermissions(BaseModel):
    """The requesting user's role + permissions for this child."""

    role: str
    is_primary: bool
    can_view: bool
    can_call: bool
    can_manage: bool


class ChildResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    nickname: str | None = None
    dob: date | None = None
    photo_url: str | None = None
    school_name: str | None = None
    class_grade: str | None = None
    active: bool
    school_mode_enabled: bool
    school_hours_from: time | None = None
    school_hours_to: time | None = None
    school_active_days: list[int]
    speed_alert_enabled: bool
    speed_threshold_kmh: int
    teen_mode_enabled: bool
    created_at: datetime
    device_count: int = 0
    permissions: ChildPermissions | None = None
