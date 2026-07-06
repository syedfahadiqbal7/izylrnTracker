import 'package:flutter_test/flutter_test.dart';

import 'package:izysafe_parent/core/i18n.dart';
import 'package:izysafe_parent/features/tracking/models.dart';

void main() {
  group('LiveLocation', () {
    test('parses lat/lng/timestamp', () {
      final l = LiveLocation.fromJson(
          {'lat': 19.07, 'lng': 72.87, 'timestamp': '2026-07-06T10:00:00Z'});
      expect(l.lat, 19.07);
      expect(l.lng, 72.87);
      expect(l.point.latitude, 19.07);
      expect(l.timestamp, isNotNull);
    });

    test('tolerates a missing timestamp', () {
      final l = LiveLocation.fromJson({'lat': 1.0, 'lng': 2.0});
      expect(l.timestamp, isNull);
    });
  });

  group('Geofence', () {
    test('parses a circle zone', () {
      final g = Geofence.fromJson({
        'id': 'g1',
        'name': 'Home',
        'zone_type': 'home',
        'type': 'circle',
        'center_lat': 19.0,
        'center_lng': 72.0,
        'radius_m': 150,
        'color': '#16AFF0',
      });
      expect(g.isCircle, isTrue);
      expect(g.isPolygon, isFalse);
      expect(g.center, isNotNull);
      expect(g.radiusM, 150);
    });

    test('parses a polygon zone', () {
      final g = Geofence.fromJson({
        'id': 'g2',
        'name': 'School',
        'zone_type': 'school',
        'type': 'polygon',
        'polygon_points': [
          {'lat': 19.0, 'lng': 72.0},
          {'lat': 19.1, 'lng': 72.0},
          {'lat': 19.1, 'lng': 72.1},
        ],
      });
      expect(g.isPolygon, isTrue);
      expect(g.polygon.length, 3);
    });
  });

  group('BusLive', () {
    test('parses position + ETA', () {
      final b = BusLive.fromJson({
        'route_id': 'r1',
        'route_name': 'Route A',
        'location': {'lat': 19.0, 'lng': 72.0, 'timestamp': '2026-07-06T10:00:00Z'},
        'stop_id': 's1',
        'stop_name': 'Gate 2',
        'eta_minutes': 7.5,
      });
      expect(b.hasPosition, isTrue);
      expect(b.etaMinutes, 7.5);
      expect(b.stopName, 'Gate 2');
    });

    test('handles a null location (no fix yet)', () {
      final b = BusLive.fromJson(
          {'route_id': 'r1', 'route_name': 'Route A', 'location': null});
      expect(b.hasPosition, isFalse);
      expect(b.point, isNull);
    });
  });

  group('SosEvent', () {
    test('parses an active SOS', () {
      final s = SosEvent.fromJson({
        'id': 'sos1',
        'child_id': 'c1',
        'child_name': 'Aanya',
        'lat': 19.0,
        'lng': 72.0,
        'approximate': true,
        'status': 'active',
        'triggered_at': '2026-07-06T10:00:00Z',
      });
      expect(s.status, 'active');
      expect(s.approximate, isTrue);
      expect(s.point, isNotNull);
    });
  });

  group('Translator', () {
    test('returns the value, then fallback, then key', () {
      const tr = Translator('en', {'map.title': 'Live Location'});
      expect(tr.t('map.title'), 'Live Location');
      expect(tr.t('missing.key', 'Fallback'), 'Fallback');
      expect(tr.t('missing.key'), 'missing.key');
    });

    test('flags RTL for Arabic only', () {
      expect(const Translator('ar', {}).isRTL, isTrue);
      expect(const Translator('en', {}).isRTL, isFalse);
    });
  });
}
