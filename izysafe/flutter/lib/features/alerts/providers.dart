import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import 'models.dart';

/// The alerts inbox (newest first). `unreadOnly` toggles the server filter; the result
/// also carries the inbox-wide unread badge count from the response `meta`.
final alertsProvider =
    FutureProvider.autoDispose.family<AlertsResult, bool>((ref, unreadOnly) async {
  final env = await ref.watch(apiClientProvider).getEnvelope('/alerts', query: {
    'unread': unreadOnly,
    'page_size': 50,
  });
  final items = (env['data'] as List)
      .map((e) => AppAlert.fromJson(e as Map<String, dynamic>))
      .toList(growable: false);
  final unread = (env['meta']?['unread_count'] as num?)?.toInt() ?? 0;
  return AlertsResult(items, unread);
});

/// Cheap unread-badge count for the Home bell (page_size 1, reads meta only).
final unreadCountProvider = FutureProvider.autoDispose<int>((ref) async {
  final env = await ref.watch(apiClientProvider).getEnvelope('/alerts', query: {
    'unread': true,
    'page_size': 1,
  });
  return (env['meta']?['unread_count'] as num?)?.toInt() ?? 0;
});

/// Mark-read actions. Both refresh the inbox + the Home badge.
final alertActionsProvider = Provider<AlertActions>((ref) {
  return AlertActions(ref);
});

class AlertActions {
  final Ref _ref;
  AlertActions(this._ref);

  Future<void> markRead(String alertId) async {
    await _ref.read(apiClientProvider).put('/alerts/$alertId/read');
    _invalidate();
  }

  Future<void> markAllRead() async {
    await _ref.read(apiClientProvider).put('/alerts/read-all');
    _invalidate();
  }

  void _invalidate() {
    _ref.invalidate(alertsProvider);
    _ref.invalidate(unreadCountProvider);
  }
}
