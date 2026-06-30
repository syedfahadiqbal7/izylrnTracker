"""Pydantic schemas for Geofence CRUD (Sprint 3 Slice 1).

Structural + cross-field shape validation lives here (→ 422 VALIDATION_ERROR).
Business rules (tier limit, polygon=Premium+) are enforced in the service layer
(→ 402). The DB CHECK constraints (schema.sql §5) remain the final backstop.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ZoneType = Literal["home", "school", "tuition", "grandparents", "sports", "other"]
GeofenceType = Literal["circle", "polygon"]

_HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"


class GeoPoint(BaseModel):
    """A single polygon vertex."""

    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


def _validate_days(v: list[int] | None) -> list[int] | None:
    if v is None:
        return v
    if not v or any(d < 1 or d > 7 for d in v) or len(set(v)) != len(v):
        raise ValueError("active_days must be unique values 1-7 (1=Mon..7=Sun)")
    return sorted(v)


def _check_shape(
    gtype: str,
    center_lat: float | None,
    center_lng: float | None,
    radius_m: int | None,
    polygon_points: list | None,
) -> None:
    """Mirror the DB shape CHECK: circle needs center+radius; polygon needs ≥3 points.

    Raises ValueError (Pydantic, on create) — the service re-runs the same rule on
    update via validate_shape() and raises APIException instead.
    """
    if gtype == "circle":
        if center_lat is None or center_lng is None or radius_m is None:
            raise ValueError("circle geofence requires center_lat, center_lng and radius_m")
    elif gtype == "polygon":
        if not polygon_points or len(polygon_points) < 3:
            raise ValueError("polygon geofence requires at least 3 polygon_points")


def validate_shape(
    gtype: str,
    center_lat: float | None,
    center_lng: float | None,
    radius_m: int | None,
    polygon_points: list | None,
) -> None:
    """Service-side shape check for updates → raises APIException(400)."""
    from app.core.errors import APIException

    try:
        _check_shape(gtype, center_lat, center_lng, radius_m, polygon_points)
    except ValueError as exc:
        raise APIException(400, "INVALID_GEOFENCE_SHAPE", str(exc))


class GeofenceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    zone_type: ZoneType = "other"
    type: GeofenceType = "circle"
    icon: str | None = Field(None, max_length=30)
    color: str | None = Field("#4CAF50", pattern=_HEX_COLOR)
    center_lat: float | None = Field(None, ge=-90, le=90)
    center_lng: float | None = Field(None, ge=-180, le=180)
    radius_m: int | None = Field(None, ge=50, le=2000)
    polygon_points: list[GeoPoint] | None = None
    address: str | None = None
    notify_enter: bool = True
    notify_exit: bool = True
    active_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])
    active_from: time | None = None
    active_to: time | None = None
    active: bool = True

    _days = field_validator("active_days")(_validate_days)

    @model_validator(mode="after")
    def _validate(self) -> GeofenceCreate:
        _check_shape(
            self.type, self.center_lat, self.center_lng, self.radius_m, self.polygon_points
        )
        if (self.active_from is None) != (self.active_to is None):
            raise ValueError("active_from and active_to must be set together")
        return self


class GeofenceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    zone_type: ZoneType | None = None
    type: GeofenceType | None = None
    icon: str | None = Field(None, max_length=30)
    color: str | None = Field(None, pattern=_HEX_COLOR)
    center_lat: float | None = Field(None, ge=-90, le=90)
    center_lng: float | None = Field(None, ge=-180, le=180)
    radius_m: int | None = Field(None, ge=50, le=2000)
    polygon_points: list[GeoPoint] | None = None
    address: str | None = None
    notify_enter: bool | None = None
    notify_exit: bool | None = None
    active_days: list[int] | None = None
    active_from: time | None = None
    active_to: time | None = None
    active: bool | None = None

    _days = field_validator("active_days")(_validate_days)


class GeofenceEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    geofence_id: uuid.UUID
    device_id: uuid.UUID | None = None
    event_type: str
    lat: float | None = None
    lng: float | None = None
    timestamp: datetime


class GeofenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    name: str
    zone_type: str
    type: str
    icon: str | None = None
    color: str | None = None
    center_lat: float | None = None
    center_lng: float | None = None
    radius_m: int | None = None
    polygon_points: list[GeoPoint] | None = None
    address: str | None = None
    notify_enter: bool
    notify_exit: bool
    active_days: list[int]
    active_from: time | None = None
    active_to: time | None = None
    active: bool
    created_at: datetime
    updated_at: datetime
