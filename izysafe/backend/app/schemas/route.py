"""Pydantic schemas for Safe Route CRUD (Sprint 7 Slice 1, F20).

Structural + cross-field validation lives here (→ 422 VALIDATION_ERROR): a route
needs ≥2 ordered waypoints, a deviation tolerance in 100–500 m, and a paired
active_from/active_to window. The Premium tier gate is enforced in the service
layer (→ 402). The DB CHECK constraints (schema.sql §6) remain the final backstop.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Waypoint(BaseModel):
    """A single route vertex. `name` is an optional label (e.g. "Home", "Gate 2")."""

    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    name: str | None = Field(None, max_length=100)


def _validate_days(v: list[int] | None) -> list[int] | None:
    if v is None:
        return v
    if not v or any(d < 1 or d > 7 for d in v) or len(set(v)) != len(v):
        raise ValueError("active_days must be unique values 1-7 (1=Mon..7=Sun)")
    return sorted(v)


class SafeRouteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    waypoints: list[Waypoint] = Field(..., min_length=2)
    deviation_tolerance_m: int = Field(200, ge=100, le=500)
    active_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    active_from: time
    active_to: time
    active: bool = True

    _days = field_validator("active_days")(_validate_days)

    @model_validator(mode="after")
    def _validate(self) -> SafeRouteCreate:
        if self.active_from == self.active_to:
            raise ValueError("active_from and active_to must differ")
        return self


class SafeRouteUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    waypoints: list[Waypoint] | None = Field(None, min_length=2)
    deviation_tolerance_m: int | None = Field(None, ge=100, le=500)
    active_days: list[int] | None = None
    active_from: time | None = None
    active_to: time | None = None
    active: bool | None = None

    _days = field_validator("active_days")(_validate_days)


class SafeRouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    name: str
    waypoints: list[Waypoint]
    deviation_tolerance_m: int
    active_days: list[int]
    active_from: time
    active_to: time
    active: bool
    created_at: datetime
    updated_at: datetime
