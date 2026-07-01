"""Pure-geometry helpers for geofence containment (Sprint 3 Slice 2).

Decision A (Sprint 3): pure Python — Haversine for circle zones, ray-casting
(even-odd / PNPOLY) for polygon zones. No PostGIS, no NumPy. These functions are
ORM-free and side-effect-free so they unit-test in isolation and run cheaply on
the webhook background path. Slice 3 wires them into breach detection through
``GeofenceService.is_point_inside``.

Coordinates are WGS-84 degrees (lat ∈ [-90, 90], lng ∈ [-180, 180]). For
city-scale zones the planar approximation used by ray-casting is far inside GPS
noise; circle distance uses the spherical Haversine formula so it stays accurate
over the 50–2000 m radius range we allow.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

EARTH_RADIUS_M = 6_371_000.0  # mean Earth radius (IUGG)

# A polygon vertex may arrive as the JSONB dict we persist ({"lat":..,"lng":..})
# or as a plain (lat, lng) pair.
PointLike = dict | Sequence[float]


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in metres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def is_inside_circle(
    lat: float, lng: float, center_lat: float, center_lng: float, radius_m: float
) -> bool:
    """True when (lat, lng) is within ``radius_m`` of the centre (boundary = inside)."""
    return haversine_m(lat, lng, center_lat, center_lng) <= radius_m


def _normalize(points: Sequence[PointLike]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in points:
        if isinstance(p, dict):
            out.append((float(p["lat"]), float(p["lng"])))
        else:
            lat, lng = p
            out.append((float(lat), float(lng)))
    return out


def _bearing_rad(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, in radians."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lng2 - lng1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return math.atan2(y, x)


def _point_to_segment_m(
    plat: float, plng: float,
    alat: float, alng: float,
    blat: float, blng: float,
) -> float:
    """Shortest great-circle distance (m) from point P to the segment A→B.

    Uses the spherical cross-track distance, clamped to the segment: if P projects
    beyond an endpoint (the foot of the perpendicular falls off the segment), the
    distance to the nearer endpoint is returned instead. Accurate to well within GPS
    noise over the city-scale segments Safe Routes use.
    """
    d_ab = haversine_m(alat, alng, blat, blng)
    if d_ab == 0.0:  # degenerate segment (A == B) → distance to the point
        return haversine_m(plat, plng, alat, alng)

    d_ap = haversine_m(alat, alng, plat, plng)
    if d_ap == 0.0:  # P sits on A
        return 0.0

    dtheta = _bearing_rad(alat, alng, plat, plng) - _bearing_rad(alat, alng, blat, blng)
    # cos(Δθ) < 0 ⇒ P projects *behind* A ⇒ A is the nearest point.
    if math.cos(dtheta) < 0:
        return d_ap

    # Cross-track (perpendicular) and along-track (from A) distances.
    dxt = math.asin(max(-1.0, min(1.0, math.sin(d_ap / EARTH_RADIUS_M) * math.sin(dtheta)))) * EARTH_RADIUS_M
    ratio = math.cos(d_ap / EARTH_RADIUS_M) / math.cos(dxt / EARTH_RADIUS_M)
    dat = math.acos(max(-1.0, min(1.0, ratio))) * EARTH_RADIUS_M
    if dat > d_ab:  # foot beyond B ⇒ B is the nearest point.
        return haversine_m(plat, plng, blat, blng)
    return abs(dxt)


def distance_to_route_m(lat: float, lng: float, waypoints: Sequence[PointLike]) -> float:
    """Minimum distance (m) from (lat, lng) to a polyline of ≥2 ordered waypoints.

    The route is the open path A→B→C…; the returned value is the smallest
    point-to-segment distance across all consecutive segments. Raises ``ValueError``
    for a degenerate route (< 2 waypoints). Drives Safe Route deviation detection
    (F20): deviation = distance > the route's tolerance.
    """
    pts = _normalize(waypoints)
    if len(pts) < 2:
        raise ValueError("route requires at least 2 waypoints")
    return min(
        _point_to_segment_m(lat, lng, a[0], a[1], b[0], b[1])
        for a, b in zip(pts, pts[1:])
    )


def is_inside_polygon(lat: float, lng: float, polygon_points: Sequence[PointLike]) -> bool:
    """Even-odd ray-casting point-in-polygon test (PNPOLY).

    ``polygon_points`` is the ordered ring of vertices (dicts or (lat, lng) pairs);
    the ring is treated as implicitly closed. Raises ``ValueError`` for a degenerate
    polygon (< 3 vertices). Behaviour exactly on an edge/vertex is implementation
    defined — acceptable for geofencing given GPS jitter dwarfs that ambiguity.
    """
    pts = _normalize(polygon_points)
    n = len(pts)
    if n < 3:
        raise ValueError("polygon requires at least 3 points")

    x, y = lng, lat  # map lng→x, lat→y
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = pts[i]
        yj, xj = pts[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside
