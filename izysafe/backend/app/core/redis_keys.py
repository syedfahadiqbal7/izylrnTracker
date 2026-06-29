"""Centralized Redis key builders + TTLs for the location pipeline (CLAUDE.md §9).

Keeping these in one place avoids drift between the webhook hot path, the 5s batch
writer, the device-status sweep, and the alert evaluators that all share this cache.
"""
from __future__ import annotations

import uuid

# ---- TTLs (seconds) --------------------------------------------------------
LOCATION_CACHE_TTL = 86_400   # location:*:latest — 24h
ONLINE_TTL = 300              # device:{id}:online — 5min sliding "live" indicator
TRACCAR_MAP_TTL = 3_600       # traccar_dev:{id} — device resolution cache, 1h

# ---- Fixed keys ------------------------------------------------------------
BATCH_LOCATIONS = "batch:locations"   # LPUSH buffer drained every 5s → PostgreSQL


# ---- Key builders ----------------------------------------------------------
def loc_child_latest(child_id: uuid.UUID | str) -> str:
    return f"location:child:{child_id}:latest"


def loc_device_latest(device_id: uuid.UUID | str) -> str:
    return f"location:device:{device_id}:latest"


def device_online(device_id: uuid.UUID | str) -> str:
    return f"device:{device_id}:online"


def traccar_device_map(traccar_id: int | str) -> str:
    return f"traccar_dev:{traccar_id}"
