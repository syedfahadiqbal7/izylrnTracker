import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import '../tracking/providers.dart' as tracking;
import 'models.dart';

/// A child's safe zones (full CRUD list).
final safeZonesProvider =
    FutureProvider.autoDispose.family<List<SafeZone>, String>((ref, childId) async {
  final data = await ref.watch(apiClientProvider).get('/children/$childId/geofences')
      as List<dynamic>;
  return data
      .map((e) => SafeZone.fromJson(e as Map<String, dynamic>))
      .toList(growable: false);
});

final geofenceActionsProvider = Provider<GeofenceActions>((ref) {
  return GeofenceActions(ref);
});

class GeofenceActions {
  final Ref _ref;
  GeofenceActions(this._ref);

  Future<void> create(String childId, Map<String, dynamic> body) async {
    await _ref.read(apiClientProvider).post('/children/$childId/geofences', body: body);
    _refresh(childId);
  }

  Future<void> update(String childId, String zoneId, Map<String, dynamic> body) async {
    await _ref.read(apiClientProvider).put('/geofences/$zoneId', body: body);
    _refresh(childId);
  }

  Future<void> delete(String childId, String zoneId) async {
    await _ref.read(apiClientProvider).delete('/geofences/$zoneId');
    _refresh(childId);
  }

  /// Refresh both the zones list and the Live Map's geofence overlay.
  void _refresh(String childId) {
    _ref.invalidate(safeZonesProvider(childId));
    _ref.invalidate(tracking.geofencesProvider(childId));
  }
}
