import 'package:flutter_test/flutter_test.dart';

import 'package:izysafe_parent/core/push.dart';
import 'package:izysafe_parent/features/alerts/models.dart';

void main() {
  group('AppAlert', () {
    test('parses an alert envelope row', () {
      final a = AppAlert.fromJson({
        'id': 'a1',
        'child_id': 'c1',
        'type': 'geofence',
        'title': 'Left the safe zone',
        'body': 'Aanya left Home',
        'data': {'child_id': 'c1', 'type': 'geofence'},
        'read': false,
        'created_at': '2026-07-06T10:00:00Z',
      });
      expect(a.type, 'geofence');
      expect(a.read, isFalse);
      expect(a.hasLocation, isTrue);
      expect(a.data['type'], 'geofence');
    });

    test('defaults missing fields safely', () {
      final a = AppAlert.fromJson({'id': 'a2', 'type': 'system'});
      expect(a.read, isFalse);
      expect(a.childId, isNull);
      expect(a.hasLocation, isFalse);
      expect(a.data, isEmpty);
    });
  });

  group('PushService.routeForData (deep-link)', () {
    test('child-scoped alert opens that child map', () {
      expect(PushService.routeForData({'child_id': 'c9', 'type': 'sos'}),
          '/child/c9/map');
    });

    test('non-child alert opens the inbox', () {
      expect(PushService.routeForData({'type': 'system'}), '/alerts');
      expect(PushService.routeForData({'child_id': ''}), '/alerts');
    });
  });
}
