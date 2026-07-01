"""Unit tests for the pure geometry engine (Sprint 3 Slice 2).

Haversine + circle/polygon containment, plus the GeofenceService.is_point_inside
dispatch. All pure/sync — no DB, Redis, or HTTP.
"""
from __future__ import annotations

import pytest

from app.core.geometry import (
    distance_to_route_m,
    haversine_m,
    is_inside_circle,
    is_inside_polygon,
)
from app.models.location import Geofence
from app.services.geofence_service import GeofenceService

# Pune-ish anchor used across circle tests.
LAT, LNG = 18.5204, 73.8567
# 1° latitude ≈ 111.32 km, so 0.001° ≈ 111.3 m due north.
DEG_LAT_M = 111_320.0

# A 1°×1° axis-aligned square (lat/lng) and a concave "L"/arrow polygon.
SQUARE = [
    {"lat": 0.0, "lng": 0.0},
    {"lat": 0.0, "lng": 1.0},
    {"lat": 1.0, "lng": 1.0},
    {"lat": 1.0, "lng": 0.0},
]
CONCAVE = [  # arrowhead pointing +lng, notch on the right side
    {"lat": 0.0, "lng": 0.0},
    {"lat": 4.0, "lng": 0.0},
    {"lat": 4.0, "lng": 4.0},
    {"lat": 2.0, "lng": 1.0},  # notch pulls the edge inward
    {"lat": 0.0, "lng": 4.0},
]


# --------------------------------------------------------------------------- #
# Haversine
# --------------------------------------------------------------------------- #
def test_haversine_zero_distance():
    assert haversine_m(LAT, LNG, LAT, LNG) == pytest.approx(0.0, abs=1e-6)


def test_haversine_one_degree_lat():
    # 1° of latitude ≈ 111.2 km (independent of longitude).
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111_195, rel=0.001)


def test_haversine_one_degree_lng_at_equator():
    # At the equator 1° of longitude ≈ 1° of latitude.
    assert haversine_m(0.0, 0.0, 0.0, 1.0) == pytest.approx(111_195, rel=0.001)


def test_haversine_symmetric():
    a = haversine_m(LAT, LNG, 19.0760, 72.8777)  # → Mumbai
    b = haversine_m(19.0760, 72.8777, LAT, LNG)
    assert a == pytest.approx(b, rel=1e-9)
    assert a == pytest.approx(118_000, rel=0.02)  # Pune↔Mumbai ≈ 118 km


# --------------------------------------------------------------------------- #
# Circle containment
# --------------------------------------------------------------------------- #
def test_circle_center_is_inside():
    assert is_inside_circle(LAT, LNG, LAT, LNG, 200) is True


def test_circle_point_inside_radius():
    # ~111 m north of centre, radius 200 m → inside.
    assert is_inside_circle(LAT + 0.001, LNG, LAT, LNG, 200) is True


def test_circle_point_outside_radius():
    # ~111 m north of centre, radius 100 m → outside.
    assert is_inside_circle(LAT + 0.001, LNG, LAT, LNG, 100) is False


def test_circle_boundary_is_inside():
    # Point exactly radius away: distance <= radius → inside.
    r = haversine_m(LAT, LNG, LAT + 0.001, LNG)
    assert is_inside_circle(LAT + 0.001, LNG, LAT, LNG, r) is True
    # A hair smaller radius excludes it.
    assert is_inside_circle(LAT + 0.001, LNG, LAT, LNG, r - 0.01) is False


# --------------------------------------------------------------------------- #
# Polygon containment (ray-casting)
# --------------------------------------------------------------------------- #
def test_polygon_point_inside_square():
    assert is_inside_polygon(0.5, 0.5, SQUARE) is True


def test_polygon_point_outside_square():
    assert is_inside_polygon(0.5, 1.5, SQUARE) is False  # east of the square
    assert is_inside_polygon(2.0, 0.5, SQUARE) is False  # north of the square


def test_polygon_accepts_lat_lng_tuples():
    tuples = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
    assert is_inside_polygon(0.5, 0.5, tuples) is True
    assert is_inside_polygon(5.0, 5.0, tuples) is False


def test_polygon_concave_notch_excluded():
    # Inside the body of the arrow.
    assert is_inside_polygon(2.0, 0.5, CONCAVE) is True
    # Inside the bounding box but within the concave notch → outside.
    assert is_inside_polygon(2.0, 3.5, CONCAVE) is False


def test_polygon_far_outside():
    assert is_inside_polygon(100.0, 100.0, SQUARE) is False


def test_polygon_too_few_points_raises():
    with pytest.raises(ValueError, match="at least 3"):
        is_inside_polygon(0.5, 0.5, [{"lat": 0.0, "lng": 0.0}, {"lat": 1.0, "lng": 1.0}])


# --------------------------------------------------------------------------- #
# Service dispatch (is_point_inside)
# --------------------------------------------------------------------------- #
def test_is_point_inside_circle():
    g = Geofence(type="circle", center_lat=LAT, center_lng=LNG, radius_m=200)
    assert GeofenceService.is_point_inside(g, LAT + 0.001, LNG) is True
    assert GeofenceService.is_point_inside(g, LAT + 0.01, LNG) is False  # ~1.1 km away


def test_is_point_inside_polygon():
    g = Geofence(type="polygon", polygon_points=SQUARE)
    assert GeofenceService.is_point_inside(g, 0.5, 0.5) is True
    assert GeofenceService.is_point_inside(g, 9.0, 9.0) is False


# --------------------------------------------------------------------------- #
# Route deviation distance (point-to-polyline)
# --------------------------------------------------------------------------- #
# A short east-west route along the equator (lng 0 → 0.01 ≈ 1.11 km at lat 0).
ROUTE = [{"lat": 0.0, "lng": 0.0}, {"lat": 0.0, "lng": 0.01}]
# An L-shaped route: east along the equator then north.
L_ROUTE = [
    {"lat": 0.0, "lng": 0.0},
    {"lat": 0.0, "lng": 0.01},
    {"lat": 0.01, "lng": 0.01},
]


def test_route_point_on_line_is_zero():
    assert distance_to_route_m(0.0, 0.005, ROUTE) == pytest.approx(0.0, abs=1e-3)


def test_route_perpendicular_offset():
    # 0.001° of latitude north of the mid-segment ≈ 111 m perpendicular.
    d = distance_to_route_m(0.001, 0.005, ROUTE)
    assert d == pytest.approx(DEG_LAT_M * 0.001, rel=0.01)


def test_route_projection_beyond_end_uses_endpoint():
    # East of B (lng 0.02, past the 0.01 endpoint): nearest point is B itself,
    # ~1.11 km away — NOT the perpendicular distance (which would be ~0).
    d = distance_to_route_m(0.0, 0.02, ROUTE)
    expected = haversine_m(0.0, 0.02, 0.0, 0.01)
    assert d == pytest.approx(expected, rel=1e-6)
    assert d > 1_000


def test_route_projection_before_start_uses_endpoint():
    # West of A (lng -0.02): nearest point is A.
    d = distance_to_route_m(0.0, -0.02, ROUTE)
    assert d == pytest.approx(haversine_m(0.0, -0.02, 0.0, 0.0), rel=1e-6)


def test_route_takes_nearest_of_multiple_segments():
    # A point near the vertical leg of the L is closer to that segment than to the
    # horizontal one; distance should reflect the nearer (vertical) leg.
    d = distance_to_route_m(0.005, 0.011, L_ROUTE)
    # ~0.001° east of the vertical leg (which sits at lng 0.01) ≈ 111 m.
    assert d == pytest.approx(DEG_LAT_M * 0.001, rel=0.05)


def test_route_too_few_waypoints_raises():
    with pytest.raises(ValueError, match="at least 2"):
        distance_to_route_m(0.0, 0.0, [{"lat": 0.0, "lng": 0.0}])


def test_route_accepts_lat_lng_tuples():
    d = distance_to_route_m(0.0, 0.005, [(0.0, 0.0), (0.0, 0.01)])
    assert d == pytest.approx(0.0, abs=1e-3)
