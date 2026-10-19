import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import 'models.dart';

/// The parent's school enrollment requests + active consents (GET /enrollments).
final enrollmentsProvider =
    FutureProvider.autoDispose<List<ParentEnrollment>>((ref) async {
  final data = await ref.watch(apiClientProvider).get('/enrollments') as List<dynamic>;
  return data
      .map((e) => ParentEnrollment.fromJson(e as Map<String, dynamic>))
      .toList(growable: false);
});

/// Count of pending (not-yet-approved) enrollment requests — for a badge/banner.
final pendingEnrollmentsCountProvider = Provider.autoDispose<int>((ref) {
  final list = ref.watch(enrollmentsProvider).valueOrNull ?? const [];
  return list.where((e) => e.pending).length;
});

/// Grant/withdraw a consent flag on one enrollment (PUT /enrollments/{id}), then
/// refresh the list. Only the provided fields are sent.
final updateConsentProvider =
    Provider<Future<void> Function(String, {bool? parentOptIn, bool? busOptIn, bool? locationOptIn})>(
        (ref) {
  final api = ref.read(apiClientProvider);
  return (id, {bool? parentOptIn, bool? busOptIn, bool? locationOptIn}) async {
    final body = <String, dynamic>{};
    if (parentOptIn != null) body['parent_opt_in'] = parentOptIn;
    if (busOptIn != null) body['bus_opt_in'] = busOptIn;
    if (locationOptIn != null) body['location_opt_in'] = locationOptIn;
    await api.put('/enrollments/$id', body: body);
    ref.invalidate(enrollmentsProvider);
  };
});
