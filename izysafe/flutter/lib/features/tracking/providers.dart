import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../auth/auth_controller.dart';
import 'models.dart';

/// Live position for a child.
///
/// Source of truth in production is Firebase RTDB `live_locations/{childId}` (the app
/// listens for < 1s updates — Flow A). Until the Firebase web config ships, this uses the
/// REST fallback `GET /children/{id}/location/latest`, polled every 5s — the same cache
/// the RTDB stream mirrors. Swapping in a Firebase `StreamProvider` here is a localized
/// change; the rest of the screen is source-agnostic.
final liveLocationProvider =
    StreamProvider.autoDispose.family<LiveLocation?, String>((ref, childId) async* {
  final api = ref.watch(apiClientProvider);
  var emitted = false;
  while (true) {
    try {
      final data = await api.get('/children/$childId/location/latest');
      final loc = (data as Map)['location'];
      yield loc == null
          ? null
          : LiveLocation.fromJson(loc as Map<String, dynamic>);
      emitted = true;
    } catch (_) {
      if (!emitted) {
        yield null; // never block the map on a transient first-fetch error
        emitted = true;
      }
    }
    await Future.delayed(const Duration(seconds: 5));
  }
});

/// A child's safe zones (geofences) — refreshed on demand.
final geofencesProvider =
    FutureProvider.autoDispose.family<List<Geofence>, String>((ref, childId) async {
  final data = await ref.watch(apiClientProvider).get('/children/$childId/geofences')
      as List<dynamic>;
  return data
      .map((e) => Geofence.fromJson(e as Map<String, dynamic>))
      .toList(growable: false);
});

/// Live bus + the child's stop + ETA. Null when the child has no `bus_opt_in`
/// (backend 404) — the screen shows a "bus tracking off" note instead of an error.
final busProvider =
    StreamProvider.autoDispose.family<BusLive?, String>((ref, childId) async* {
  final api = ref.watch(apiClientProvider);
  while (true) {
    try {
      final data = await api.get('/children/$childId/bus');
      yield BusLive.fromJson(data as Map<String, dynamic>);
    } on ApiException catch (e) {
      if (e.status == 404 || e.status == 403) {
        yield null; // not opted into bus tracking
      }
      // other errors: keep the last value
    } catch (_) {
      // transient: keep the last value
    }
    await Future.delayed(const Duration(seconds: 8));
  }
});

/// Active SOS events across all the parent's children (polled). The map filters to the
/// child in view. The real *trigger* is the watch's alarm (Flow C) — this is read-only.
final activeSosProvider =
    StreamProvider.autoDispose<List<SosEvent>>((ref) async* {
  final api = ref.watch(apiClientProvider);
  var emitted = false;
  while (true) {
    try {
      final data = await api.get('/sos/active') as List<dynamic>;
      yield data
          .map((e) => SosEvent.fromJson(e as Map<String, dynamic>))
          .toList(growable: false);
      emitted = true;
    } catch (_) {
      if (!emitted) {
        yield const [];
        emitted = true;
      }
    }
    await Future.delayed(const Duration(seconds: 8));
  }
});

/// Resolve an SOS (any family member). Clears the shared alarm for every parent.
final resolveSosProvider = Provider<Future<void> Function(String)>((ref) {
  final api = ref.watch(apiClientProvider);
  return (sosId) async {
    await api.put('/sos/$sosId/resolve');
    ref.invalidate(activeSosProvider);
  };
});
