import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import '../children/children_providers.dart';
import 'models.dart';

/// A child's paired devices (full CRUD list).
final devicesProvider =
    FutureProvider.autoDispose.family<List<Device>, String>((ref, childId) async {
  final data = await ref.watch(apiClientProvider).get('/children/$childId/devices')
      as List<dynamic>;
  return data
      .map((e) => Device.fromJson(e as Map<String, dynamic>))
      .toList(growable: false);
});

final deviceActionsProvider = Provider<DeviceActions>((ref) {
  return DeviceActions(ref);
});

class DeviceActions {
  final Ref _ref;
  DeviceActions(this._ref);

  Future<void> add(String childId, Map<String, dynamic> body) async {
    await _ref.read(apiClientProvider).post('/children/$childId/devices', body: body);
    _refresh(childId);
  }

  Future<void> update(String childId, String deviceId, Map<String, dynamic> body) async {
    await _ref.read(apiClientProvider).put('/devices/$deviceId', body: body);
    _refresh(childId);
  }

  Future<void> remove(String childId, String deviceId) async {
    await _ref.read(apiClientProvider).delete('/devices/$deviceId');
    _refresh(childId);
  }

  /// Refresh the device list + the home child cards (their device_count badge).
  void _refresh(String childId) {
    _ref.invalidate(devicesProvider(childId));
    _ref.invalidate(childrenProvider);
  }
}
