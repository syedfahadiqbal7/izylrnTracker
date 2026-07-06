import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

/// A child's safe zone (geofence) with the full CRUD field set.
class SafeZone {
  final String id;
  final String name;
  final String zoneType; // home/school/tuition/grandparents/sports/other
  final String type; // circle | polygon
  final double? centerLat;
  final double? centerLng;
  final int? radiusM;
  final List<LatLng> polygon;
  final String color; // hex string, e.g. "#16AFF0"
  final bool notifyEnter;
  final bool notifyExit;
  final bool active;
  final String? address;

  const SafeZone({
    required this.id,
    required this.name,
    required this.zoneType,
    required this.type,
    required this.centerLat,
    required this.centerLng,
    required this.radiusM,
    required this.polygon,
    required this.color,
    required this.notifyEnter,
    required this.notifyExit,
    required this.active,
    required this.address,
  });

  bool get isCircle =>
      type == 'circle' && centerLat != null && centerLng != null && radiusM != null;
  bool get isPolygon => type == 'polygon' && polygon.length >= 3;
  LatLng? get center =>
      (centerLat != null && centerLng != null) ? LatLng(centerLat!, centerLng!) : null;
  Color get colorValue => parseHexColor(color);

  factory SafeZone.fromJson(Map<String, dynamic> j) {
    final pts = (j['polygon_points'] as List?) ?? const [];
    return SafeZone(
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
      color: (j['color'] ?? '#16AFF0') as String,
      notifyEnter: (j['notify_enter'] ?? true) as bool,
      notifyExit: (j['notify_exit'] ?? true) as bool,
      active: (j['active'] ?? true) as bool,
      address: j['address'] as String?,
    );
  }
}

/// The zone types the parent can pick from (matches the backend ZoneType enum).
const zoneTypes = <String>[
  'home',
  'school',
  'tuition',
  'grandparents',
  'sports',
  'other',
];

IconData zoneTypeIcon(String zt) {
  switch (zt) {
    case 'home':
      return Icons.home_rounded;
    case 'school':
      return Icons.school_rounded;
    case 'tuition':
      return Icons.menu_book_rounded;
    case 'grandparents':
      return Icons.family_restroom_rounded;
    case 'sports':
      return Icons.sports_soccer_rounded;
    default:
      return Icons.place_rounded;
  }
}

/// The colour palette offered in the editor (izyLrn brand-aligned).
const zoneColors = <String>[
  '#16AFF0', // cyan
  '#2C56EE', // indigo
  '#6609E3', // violet
  '#22C55E', // green
  '#F59E0B', // amber
  '#E11D48', // rose
];

Color parseHexColor(String hex) {
  var h = hex.replaceFirst('#', '').trim();
  if (h.length == 6) h = 'FF$h';
  final v = int.tryParse(h, radix: 16);
  return v == null ? const Color(0xFF16AFF0) : Color(v);
}
