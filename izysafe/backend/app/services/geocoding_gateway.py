"""Reverse-geocoding gateway (Sprint 7 Slice 5, F24 — Safe Addresses).

Turns a lat/lng into a human-readable street address via the Google Maps Geocoding
API, used to auto-label a Safe Address / geofence when the parent doesn't type one.

Mirrors the other external gateways (Traccar/Fcm/Realtime): the network call lives
here so tests swap a fake via a FastAPI dependency override, and it **never raises** —
it returns ``None`` when unconfigured (no API key), on any network/parse error, or when
Google finds no address. A null address is always acceptable (the column is nullable),
so reverse-geocoding is strictly best-effort and never blocks a create from succeeding.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("izysafe.geocoding")

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


class GeocodingGateway:
    """Default production gateway. Construct once per request (cheap)."""

    async def reverse_geocode(self, lat: float, lng: float) -> str | None:
        """Return the formatted street address for (lat, lng), or None. Never raises.
        Bounded by a short timeout so it can't stall a create request."""
        if not settings.google_maps_api_key:
            return None  # unconfigured → best-effort no-op
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(
                    _GEOCODE_URL,
                    params={"latlng": f"{lat},{lng}", "key": settings.google_maps_api_key},
                )
            data = resp.json()
            if data.get("status") == "OK" and data.get("results"):
                return data["results"][0].get("formatted_address")
            logger.warning("Reverse geocode returned status=%s", data.get("status"))
        except (httpx.HTTPError, ValueError, KeyError):
            logger.warning("Reverse geocode failed for %s,%s", lat, lng)
        return None
