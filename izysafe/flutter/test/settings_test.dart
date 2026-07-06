import 'package:flutter_test/flutter_test.dart';

import 'package:izysafe_parent/features/settings/models.dart';

void main() {
  group('ProfileSettings', () {
    test('parses profile with quiet hours (HH:MM:SS → HH:MM)', () {
      final p = ProfileSettings.fromJson({
        'id': 'u1',
        'phone': '+919888000001',
        'name': 'Priya Kapoor',
        'email': 'priya@example.com',
        'photo_url': null,
        'language': 'hi',
        'subscription_tier': 'premium',
        'quiet_hours_from': '22:00:00',
        'quiet_hours_to': '07:00:00',
      });
      expect(p.quietHoursOn, isTrue);
      expect(p.quietFrom, '22:00');
      expect(p.quietTo, '07:00');
      expect(p.tier, 'premium');
      expect(p.initials, 'PK');
      expect(p.displayName, 'Priya Kapoor');
    });

    test('handles no name (falls back to phone) + no quiet hours', () {
      final p = ProfileSettings.fromJson({
        'id': 'u2',
        'phone': '+919888000002',
        'language': 'en',
        'subscription_tier': 'free',
      });
      expect(p.quietHoursOn, isFalse);
      expect(p.displayName, '+919888000002');
      expect(p.tier, 'free');
    });
  });

  group('SubscriptionInfo', () {
    test('parses an active paid subscription', () {
      final s = SubscriptionInfo.fromJson({
        'tier': 'premium',
        'status': 'active',
        'is_active_paid': true,
        'current_period_end': '2026-08-01T00:00:00Z',
      });
      expect(s.tier, 'premium');
      expect(s.isActivePaid, isTrue);
      expect(s.periodEnd, isNotNull);
    });

    test('parses a free plan', () {
      final s = SubscriptionInfo.fromJson(
          {'tier': 'free', 'status': 'free', 'is_active_paid': false});
      expect(s.isActivePaid, isFalse);
      expect(s.periodEnd, isNull);
    });
  });

  group('EmergencyContact', () {
    test('parses with child name', () {
      final c = EmergencyContact.fromJson({
        'id': 'e1',
        'child_id': 'c1',
        'name': 'Uncle Raj',
        'phone': '+919812345678',
        'relationship': 'Uncle',
      }, 'Aanya');
      expect(c.childName, 'Aanya');
      expect(c.relationship, 'Uncle');
    });
  });
}
