"""Schemas for the Traccar position-forward webhook (Flow A).

Traccar's `forward.type=json` POSTs a body shaped like:
    {"position": {... "deviceId": 7, "attributes": {...}}, "device": {"uniqueId": "<imei>"}}

We parse leniently (extra="ignore") and only pull the fields the pipeline needs.
Units note: Traccar reports `speed` in **knots** and `course` as the bearing in
degrees; battery percent arrives as `attributes.batteryLevel`.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TraccarAttributes(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    battery_level: float | None = Field(default=None, alias="batteryLevel")  # percent 0–100
    battery: float | None = None  # often voltage; fallback only
    motion: bool | None = None
    alarm: str | None = None  # GT06 alarm type, e.g. "sos" (drives the alarm webhook)


class TraccarPositionIn(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    device_id: int = Field(alias="deviceId")
    protocol: str | None = None
    latitude: float
    longitude: float
    altitude: float | None = None
    speed: float | None = None   # knots
    course: float | None = None  # bearing, degrees
    accuracy: float | None = None
    valid: bool = True
    fix_time: datetime | None = Field(default=None, alias="fixTime")
    device_time: datetime | None = Field(default=None, alias="deviceTime")
    server_time: datetime | None = Field(default=None, alias="serverTime")
    address: str | None = None
    attributes: TraccarAttributes = Field(default_factory=TraccarAttributes)

    @property
    def best_time(self) -> datetime | None:
        """Most trustworthy fix time available (GPS fix > device clock > server)."""
        return self.fix_time or self.device_time or self.server_time

    @property
    def battery_pct(self) -> int | None:
        """Battery as an integer percentage, clamped to 0–100, or None if absent."""
        raw = self.attributes.battery_level
        if raw is None:
            return None
        return max(0, min(100, int(round(raw))))

    @property
    def speed_kmh(self) -> float | None:
        """Speed in km/h (Traccar reports knots), or None if absent."""
        if self.speed is None:
            return None
        return round(self.speed * 1.852, 1)


class TraccarDeviceIn(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: int | None = None
    unique_id: str | None = Field(default=None, alias="uniqueId")  # the IMEI
    name: str | None = None
    status: str | None = None


class TraccarForward(BaseModel):
    """Top-level body Traccar forwards for every decoded position."""

    model_config = ConfigDict(extra="ignore")

    position: TraccarPositionIn
    device: TraccarDeviceIn | None = None
