import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

/// A single live position (from Firebase RTDB `live_locations/{child}` or the
/// `/children/{id}/location/latest` REST fallback).
class LiveLocation {
  final double lat;
  final double lng;
  final DateTime? timestamp;
  const LiveLocation({required this.lat, required this.lng, this.timestamp});

  LatLng get point => LatLng(lat, lng);

  factory LiveLocation.fromJson(Map<String, dynamic> j) => LiveLocation(
        lat: (j['lat'] as num).toDouble(),
        lng: (j['lng'] as num).toDouble(),
        timestamp: j['timestamp'] != null
            ? DateTime.tryParse('${j['timestamp']}')?.toLocal()
            : null,
      );
}

/// A safe zone / geofence overlay.
class Geofence {
  final String id;
  final String name;
  final String zoneType; // home/school/tuition/…
  final String type; // circle | polygon
  final double? centerLat;
  final double? centerLng;
  final int? radiusM;
  final List<LatLng> polygon;
  final Color color;

  const Geofence({
    required this.id,
    required this.name,
    required this.zoneType,
    required this.type,
    required this.centerLat,
    required this.centerLng,
    required this.radiusM,
    required this.polygon,
    required this.color,
  });

  bool get isCircle =>
      type == 'circle' && centerLat != null && centerLng != null && radiusM != null;
  bool get isPolygon => type == 'polygon' && polygon.length >= 3;
  LatLng? get center =>
      (centerLat != null && centerLng != null) ? LatLng(centerLat!, centerLng!) : null;

  factory Geofence.fromJson(Map<String, dynamic> j) {
    final pts = (j['polygon_points'] as List?) ?? const [];
    return Geofence(
      id: j['id'] as String,
      name: (j['name'] ?? '') as String,
      zoneType: (j['zone_type'] ?? 'other') as String,
      type: (j['type'] ?? 'circle') as String,
      centerLat: (j['center_lat'] as num?)?.toDouble(),
      centerLng: (j['center_lng'] as num?)?.toDouble(),
      radiusM: (j['radius_m'] as num?)?.toInt(),
      polygon: pts
          .map((p) => LatLng(
              (p['lat'] as num).toDouble(), (p['lng'] as num).toDouble()))
          .toList(growable: false),
      color: _parseColor(j['color'] as String?),
    );
  }
}

/// Live bus position + the child's stop + a straight-line ETA (F28).
class BusLive {
  final String routeId;
  final String routeName;
  final double? lat;
  final double? lng;
  final DateTime? timestamp;
  final String? stopId;
  final String? stopName;
  final double? etaMinutes;

  const BusLive({
    required this.routeId,
    required this.routeName,
    required this.lat,
    required this.lng,
    required this.timestamp,
    required this.stopId,
    required this.stopName,
    required this.etaMinutes,
  });

  bool get hasPosition => lat != null && lng != null;
  LatLng? get point => hasPosition ? LatLng(lat!, lng!) : null;

  factory BusLive.fromJson(Map<String, dynamic> j) {
    final loc = j['location'] as Map<String, dynamic>?;
    return BusLive(
      routeId: j['route_id'] as String,
      routeName: (j['route_name'] ?? '') as String,
      lat: (loc?['lat'] as num?)?.toDouble(),
      lng: (loc?['lng'] as num?)?.toDouble(),
      timestamp: loc?['timestamp'] != null
          ? DateTime.tryParse('${loc!['timestamp']}')?.toLocal()
          : null,
      stopId: j['stop_id'] as String?,
      stopName: j['stop_name'] as String?,
      etaMinutes: (j['eta_minutes'] as num?)?.toDouble(),
    );
  }
}

/// An active SOS emergency for one of the parent's children (Flow C).
class SosEvent {
  final String id;
  final String childId;
  final String? childName;
  final double? lat;
  final double? lng;
  final bool approximate;
  final String status;
  final DateTime triggeredAt;

  const SosEvent({
    required this.id,
    required this.childId,
    required this.childName,
    required this.lat,
    required this.lng,
    required this.approximate,
    required this.status,
    required this.triggeredAt,
  });

  LatLng? get point =>
      (lat != null && lng != null) ? LatLng(lat!, lng!) : null;

  factory SosEvent.fromJson(Map<String, dynamic> j) => SosEvent(
        id: j['id'] as String,
        childId: j['child_id'] as String,
        childName: j['child_name'] as String?,
        lat: (j['lat'] as num?)?.toDouble(),
        lng: (j['lng'] as num?)?.toDouble(),
        approximate: (j['approximate'] ?? false) as bool,
        status: (j['status'] ?? 'active') as String,
        triggeredAt:
            DateTime.tryParse('${j['triggered_at']}')?.toLocal() ?? DateTime(2000),
      );
}

Color _parseColor(String? hex) {
  if (hex == null) return const Color(0xFF2C56EE);
  var h = hex.replaceFirst('#', '').trim();
  if (h.length == 6) h = 'FF$h';
  final v = int.tryParse(h, radix: 16);
  return v == null ? const Color(0xFF2C56EE) : Color(v);
}
