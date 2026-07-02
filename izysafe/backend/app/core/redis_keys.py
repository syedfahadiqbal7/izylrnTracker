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
LASTSEEN_TTL = 86_400         # device:{id}:lastseen — receipt epoch, 24h
STATUS_TTL = 86_400           # device:{id}:status — persisted online/offline marker
GEOFENCE_STATE_TTL = 259_200  # geofence:{child}:{fence}:inside — 72h (Flow B)
ACTIVE_FENCES_TTL = 3_600     # active_fences:{child} — cached active fence set, 1h backstop
ROUTE_STATE_TTL = 259_200     # route:{child}:{route}:deviating — 72h (Safe Routes, F20)
ACTIVE_ROUTES_TTL = 3_600     # active_routes:{child} — cached active route set, 1h backstop

WATCH_REMOVED_SINCE_TTL = 86_400  # watch_removed:{device}:since — 24h episode cap (F18)

# ---- Fixed keys ------------------------------------------------------------
BATCH_LOCATIONS = "batch:locations"   # LPUSH buffer drained every 5s → PostgreSQL
WATCH_REMOVED_PENDING = "watch_removed:pending"  # SET of device_ids currently removed (F18)


# ---- Key builders ----------------------------------------------------------
def loc_child_latest(child_id: uuid.UUID | str) -> str:
    return f"location:child:{child_id}:latest"


def loc_device_latest(device_id: uuid.UUID | str) -> str:
    return f"location:device:{device_id}:latest"


def device_online(device_id: uuid.UUID | str) -> str:
    return f"device:{device_id}:online"


def device_lastseen(device_id: uuid.UUID | str) -> str:
    """Epoch seconds of the last position we *received* (liveness, not fix time)."""
    return f"device:{device_id}:lastseen"


def device_status(device_id: uuid.UUID | str) -> str:
    """Last persisted is_online state ('online'/'offline') — fast-path to avoid a
    DB read on every position when reconciling the online transition."""
    return f"device:{device_id}:status"


def traccar_device_map(traccar_id: int | str) -> str:
    return f"traccar_dev:{traccar_id}"


def watch_removed_since(device_id: uuid.UUID | str) -> str:
    """Epoch when a device's removal (tamper) alarm was first seen this episode (F18);
    the sweep fires `watch_removed` once now − since ≥ the device threshold. Cleared on
    a re-wear signal; presence in WATCH_REMOVED_PENDING marks it as awaiting the sweep."""
    return f"watch_removed:{device_id}:since"


def battery_alerted(device_id: uuid.UUID | str) -> str:
    """Debounce marker storing the last battery level alerted ('low'/'critical')."""
    return f"battery_alerted:{device_id}"


def speed_count(child_id: uuid.UUID | str) -> str:
    """Sliding-window counter of consecutive over-threshold speed samples."""
    return f"speed_count:{child_id}"


def speed_alerted(child_id: uuid.UUID | str) -> str:
    """Debounce marker after a speed alert fires."""
    return f"speed_alerted:{child_id}"


def geofence_inside(child_id: uuid.UUID | str, fence_id: uuid.UUID | str) -> str:
    """Last-known inside/outside state ('true'/'false') per child+fence (Flow B)."""
    return f"geofence:{child_id}:{fence_id}:inside"


def geofence_debounce(child_id: uuid.UUID | str, fence_id: uuid.UUID | str) -> str:
    """5-min anti-jitter debounce after a breach alert fires for a child+fence."""
    return f"geofence_debounce:{child_id}:{fence_id}"


def active_fences(child_id: uuid.UUID | str) -> str:
    """Cached active-fence bundle for a child (Decision E); invalidated on CRUD."""
    return f"active_fences:{child_id}"


def route_deviating(child_id: uuid.UUID | str, route_id: uuid.UUID | str) -> str:
    """Last-known on-route/off-route state ('true'=deviating/'false') per child+route
    (Safe Routes, F20). Mirrors geofence_inside — always advanced so a suppressed
    transition can't re-fire later."""
    return f"route:{child_id}:{route_id}:deviating"


def route_debounce(child_id: uuid.UUID | str, route_id: uuid.UUID | str) -> str:
    """5-min anti-jitter debounce after a route-deviation alert fires per child+route."""
    return f"route_debounce:{child_id}:{route_id}"


def active_routes(child_id: uuid.UUID | str) -> str:
    """Cached active-route bundle for a child (F20); invalidated on CRUD."""
    return f"active_routes:{child_id}"


def pickup_recorded(child_id: uuid.UUID | str, day: str) -> str:
    """Once-per-day dedup marker after a pickup is recorded (F17). `day` is the local
    YYYYMMDD in the primary parent's tz; the key expires at the next local midnight."""
    return f"pickup:{child_id}:{day}"


def share_view_rate(ip: str) -> str:
    """Per-IP sliding counter for public share-link views (F22 abuse guard, 60s window)."""
    return f"rate:share:{ip}"


def sos_active(child_id: uuid.UUID | str) -> str:
    """Set while a child has an active SOS (dedup + fast 'is-active' check); cleared
    on resolve. Flow C."""
    return f"sos:{child_id}:active"


def sound_sessions(child_id: uuid.UUID | str) -> str:
    """Daily Sound Around (F11) session counter per child; expires at the next
    midnight in the primary parent's timezone (3/child/day gate, Sprint 5)."""
    return f"sound_sessions:{child_id}"


def call_active(child_id: uuid.UUID | str) -> str:
    """Set while a Two-way Call (F12) is presumed in progress for a child — a bounded
    no-active-call guard (no hang-up signal exists; TTL-expired, Sprint 5)."""
    return f"call:{child_id}:active"


def bus_stop_debounce(route_id: uuid.UUID | str, stop_id: uuid.UUID | str) -> str:
    """Anti-repeat marker after a bus_arrival fires for a route+stop (F28, 5 min)."""
    return f"bus_stop_debounce:{route_id}:{stop_id}"


def school_login_rate(email: str) -> str:
    """Per-email failed-login counter (school-admin brute-force guard, Sprint 8)."""
    return f"rate:schoollogin:{email.lower()}"


def pwreset_token(token_hash: str) -> str:
    """Single-use school-admin password-reset token, keyed by its SHA-256 (Sprint 9);
    value = admin id, self-expiring at the token TTL."""
    return f"pwreset:{token_hash}"


def pwreset_rate_email(email: str) -> str:
    """Per-email forgot-password request counter (Sprint 9)."""
    return f"rate:pwreset:{email.lower()}"


def pwreset_rate_ip(ip: str) -> str:
    """Per-IP forgot-password request counter (Sprint 9)."""
    return f"rate:pwreset:ip:{ip}"


def pwchange_rate(admin_id: uuid.UUID | str) -> str:
    """Per-admin change-password attempt counter (Sprint 9 Slice 2 abuse guard)."""
    return f"rate:pwchange:{admin_id}"


def gateway_event(gateway: str, event_id: str) -> str:
    """Idempotency marker for a processed payment-gateway webhook event (Sprint 6);
    dedups gateway retries so activation alerts don't double-fire."""
    return f"payevt:{gateway}:{event_id}"
