import 'package:flutter_test/flutter_test.dart';

import 'package:izysafe_parent/features/geofences/models.dart';

void main() {
  group('SafeZone', () {
    test('parses a circle zone with notify flags', () {
      final z = SafeZone.fromJson({
        'id': 'z1',
        'name': 'Home',
        'zone_type': 'home',
        'type': 'circle',
        'center_lat': 19.07,
        'center_lng': 72.87,
        'radius_m': 200,
        'color': '#16AFF0',
        'notify_enter': true,
        'notify_exit': false,
        'active': true,
      });
      expect(z.isCircle, isTrue);
      expect(z.isPolygon, isFalse);
      expect(z.radiusM, 200);
      expect(z.notifyEnter, isTrue);
      expect(z.notifyExit, isFalse);
      expect(z.center, isNotNull);
    });

    test('parses a polygon zone', () {
      final z = SafeZone.fromJson({
        'id': 'z2',
        'name': 'Park',
        'zone_type': 'sports',
        'type': 'polygon',
        'polygon_points': [
          {'lat': 19.0, 'lng': 72.0},
          {'lat': 19.1, 'lng': 72.0},
          {'lat': 19.1, 'lng': 72.1},
        ],
        'active': false,
      });
      expect(z.isPolygon, isTrue);
      expect(z.polygon.length, 3);
      expect(z.active, isFalse);
    });

    test('defaults notify flags + color when absent', () {
      final z = SafeZone.fromJson(
          {'id': 'z3', 'name': 'X', 'type': 'circle', 'center_lat': 1.0, 'center_lng': 2.0, 'radius_m': 60});
      expect(z.notifyEnter, isTrue);
      expect(z.notifyExit, isTrue);
      expect(z.color, '#16AFF0');
    });
  });

  test('parseHexColor handles #RRGGBB and bad input', () {
    expect(parseHexColor('#22C55E').toARGB32(), 0xFF22C55E);
    expect(parseHexColor('nonsense').toARGB32(), 0xFF16AFF0);
  });
}
