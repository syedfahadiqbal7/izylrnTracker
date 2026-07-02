"""Pydantic schemas for bus roster & routes (Sprint 8 Slice 4, F28).

Drivers, routes, ordered stops, and child↔route assignments — all school-scoped
(the owning school is derived from the authenticated admin, never the payload).
"""
from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field


# ------------------------------------------------------------------ drivers
class DriverCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=20)
    verified: bool = False
    access_code: str | None = Field(None, min_length=6, max_length=100)  # optional login code


class DriverUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=20)
    verified: bool | None = None
    active: bool | None = None


class DriverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    phone: str | None = None
    verified: bool
    active: bool
    created_at: datetime


# ------------------------------------------------------------------- routes
class RouteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    driver_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None      # a device_type='bus' device (Slice 5 wires live tracking)
    active_from: time | None = None
    active_to: time | None = None


class RouteUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    driver_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    active_from: time | None = None
    active_to: time | None = None
    active: bool | None = None


class RouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    driver_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    active_from: time | None = None
    active_to: time | None = None
    active: bool
    created_at: datetime


# -------------------------------------------------------------------- stops
class StopCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    seq: int = Field(..., ge=1)
    scheduled_at: time | None = None


class StopUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    seq: int | None = Field(None, ge=1)
    scheduled_at: time | None = None


class StopResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    route_id: uuid.UUID
    name: str
    lat: float
    lng: float
    seq: int
    scheduled_at: time | None = None


# -------------------------------------------------------------- assignments
class AssignmentCreate(BaseModel):
    enrollment_id: uuid.UUID           # the student to assign (must be enrolled + consented)
    stop_id: uuid.UUID | None = None   # their boarding stop on this route


class AssignmentResponse(BaseModel):
    id: uuid.UUID
    route_id: uuid.UUID
    child_id: uuid.UUID
    child_name: str
    stop_id: uuid.UUID | None = None


# ------------------------------------------------------------- bus devices
class BusDeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    imei: str = Field(..., min_length=5, max_length=20)
    traccar_id: int | None = None
    model: str | None = Field(None, max_length=100)


class BusDeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    imei: str
    traccar_id: int | None = None
    is_online: bool
    created_at: datetime


# ------------------------------------------------------- driver app (S10)
class DriverSetCodeRequest(BaseModel):
    access_code: str = Field(..., min_length=6, max_length=100)


class DriverLoginRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=20)
    code: str = Field(..., min_length=1, max_length=100)


class DriverProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    phone: str | None = None
    verified: bool
    active: bool
    last_login_at: datetime | None = None


class DriverRouteStop(BaseModel):
    id: uuid.UUID
    name: str
    lat: float
    lng: float
    seq: int
    scheduled_at: time | None = None


class DriverRosterEntry(BaseModel):
    child_id: uuid.UUID
    child_name: str
    stop_id: uuid.UUID | None = None


class DriverRouteResponse(BaseModel):
    route_id: uuid.UUID
    name: str
    active_from: time | None = None
    active_to: time | None = None
    active: bool
    device_id: uuid.UUID | None = None
    active_trip: dict | None = None          # {trip_id, started_at} while a trip is running
    stops: list[DriverRouteStop]
    roster: list[DriverRosterEntry]


class TripStartRequest(BaseModel):
    route_id: uuid.UUID


class TripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    route_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    status: str
    started_at: datetime
    ended_at: datetime | None = None


class BoardingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trip_id: uuid.UUID
    child_id: uuid.UUID
    stop_id: uuid.UUID | None = None
    boarded_at: datetime


# --------------------------------------------------- parent-facing live bus
class BusLiveResponse(BaseModel):
    route_id: uuid.UUID
    route_name: str
    location: dict | None = None      # {lat, lng, timestamp} from the live cache, or None
    stop_id: uuid.UUID | None = None
    stop_name: str | None = None
    eta_minutes: float | None = None  # straight-line estimate to the child's stop

