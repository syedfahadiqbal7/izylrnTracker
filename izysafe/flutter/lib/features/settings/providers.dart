import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import '../children/children_providers.dart';
import 'models.dart';

/// The parent's profile + notification preferences.
final profileProvider = FutureProvider.autoDispose<ProfileSettings>((ref) async {
  final data = await ref.watch(apiClientProvider).get('/auth/me');
  return ProfileSettings.fromJson(data as Map<String, dynamic>);
});

/// The parent's current plan / subscription state.
/// The sellable plan catalog, priced in the user's currency (GET /subscriptions/plans).
final plansProvider = FutureProvider.autoDispose<List<Plan>>((ref) async {
  final data =
      await ref.watch(apiClientProvider).get('/subscriptions/plans') as List<dynamic>;
  return data
      .map((e) => Plan.fromJson(e as Map<String, dynamic>))
      .toList(growable: false);
});

final subscriptionProvider =
    FutureProvider.autoDispose<SubscriptionInfo>((ref) async {
  final data = await ref.watch(apiClientProvider).get('/subscriptions/me');
  return SubscriptionInfo.fromJson(data as Map<String, dynamic>);
});

/// Emergency contacts across the parent's children (Premium, per-child). Children
/// that 402/403/404 (not premium / no access) are skipped so the section degrades
/// gracefully into an upsell rather than an error.
final emergencyContactsProvider =
    FutureProvider.autoDispose<List<EmergencyContact>>((ref) async {
  final api = ref.watch(apiClientProvider);
  final children = await ref.watch(childrenProvider.future);
  final out = <EmergencyContact>[];
  for (final child in children) {
    try {
      final rows =
          await api.get('/children/${child.id}/emergency-contacts') as List;
      out.addAll(rows.map((e) =>
          EmergencyContact.fromJson(e as Map<String, dynamic>, child.name)));
    } catch (_) {
      // not premium / no access for this child — skip
    }
  }
  return out;
});

/// Profile / preference mutations. All refresh the profile + the auth user.
final settingsActionsProvider = Provider<SettingsActions>((ref) {
  return SettingsActions(ref);
});

class SettingsActions {
  final Ref _ref;
  SettingsActions(this._ref);

  Future<void> _update(Map<String, dynamic> body) async {
    await _ref.read(apiClientProvider).put('/auth/me', body: body);
    _ref.invalidate(profileProvider);
    await _ref.read(authControllerProvider.notifier).loadUser();
  }

  Future<void> updateProfile({String? name, String? email}) {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (email != null) body['email'] = email;
    return _update(body);
  }

  /// Save the full contact profile from the Profile edit screen. Sends every field
  /// explicitly (nulls clear them). `additionalContacts` is a list of {label, phone}.
  Future<void> saveProfile({
    required String? name,
    required String? email,
    required String? address,
    required double? homeLat,
    required double? homeLng,
    required List<Map<String, String>> additionalContacts,
  }) {
    return _update({
      'name': name,
      'email': email,
      'address': address,
      'home_lat': homeLat,
      'home_lng': homeLng,
      'additional_contacts': additionalContacts,
    });
  }

  /// Sync the app language to the backend (so pushes/emails localize too). Local
  /// persistence + RTL is handled by the i18n LocaleController separately.
  Future<void> setLanguage(String code) => _update({'language': code});

  /// Set or clear the notification quiet-hours window ("HH:MM" strings, or null/null).
  Future<void> setQuietHours(String? from, String? to) =>
      _update({'quiet_hours_from': from, 'quiet_hours_to': to});

  /// Start a checkout for a tier. Returns the gateway checkout URL to open, or null
  /// if none was issued. Throws if the payment gateway isn't configured yet.
  Future<String?> startCheckout(String tier) async {
    final data = await _ref
        .read(apiClientProvider)
        .post('/subscriptions/checkout', body: {'tier': tier});
    return (data as Map<String, dynamic>)['checkout_url'] as String?;
  }
}
