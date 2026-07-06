"""Pydantic schemas for parent-facing device pairing & management (Sprint 11).

A device is a child's GPS tracker (watch / bag_tracker / phone) — the hardware that
feeds Flow A live location. Pairing creates the local `devices` row **and** registers
the tracker in Traccar so its incoming fixes resolve to us. Bus devices are school-scoped
and handled separately (schemas/bus.py); these schemas never accept `device_type='bus'`.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Enum values kept in sync with the devices CHECK constraints (models/device.py).
DeviceType = Literal["watch", "bag_tracker", "phone"]
Protocol = Literal["gt06", "tk103", "h02"]
# battery_threshold ∈ {10,15,20,30}; watch_removed_threshold_min ∈ {5,10,15} (DB CHECKs).
BatteryThreshold = Literal[10, 15, 20, 30]
RemovedThreshold = Literal[5, 10, 15]


class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)  # e.g. "Aryan's Watch"
    imei: str = Field(..., min_length=5, max_length=20)   # from the tracker / its QR code
    device_type: DeviceType = "watch"
    model: str | None = Field(None, max_length=100)
    color: str | None = Field(None, max_length=30)
    protocol: Protocol = "gt06"
    battery_threshold: BatteryThreshold = 20
    watch_removed_threshold_min: RemovedThreshold = 10
    watch_removed_enabled: bool = False


class DeviceUpdate(BaseModel):
    """All optional — a partial update (exclude_unset). IMEI/type are immutable once paired."""

    name: str | None = Field(None, min_length=1, max_length=100)
    model: str | None = Field(None, max_length=100)
    color: str | None = Field(None, max_length=30)
    battery_threshold: BatteryThreshold | None = None
    watch_removed_threshold_min: RemovedThreshold | None = None
    watch_removed_enabled: bool | None = None
    active: bool | None = None


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID | None = None
    name: str
    device_type: str
    imei: str
    traccar_id: int | None = None      # null until Traccar registration succeeds (graceful seam)
    model: str | None = None
    color: str | None = None
    protocol: str | None = None
    battery_threshold: int
    watch_removed_threshold_min: int
    watch_removed_enabled: bool
    last_battery: int | None = None
    last_seen_at: datetime | None = None
    is_online: bool                    # live: derived from the Redis online marker on read
    active: bool
    created_at: datetime
