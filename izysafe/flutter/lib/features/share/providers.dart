import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import 'models.dart';

/// A child's active share links (backend returns most-recent-first; we keep only
/// the still-valid ones — non-revoked, non-expired).
final shareLinksProvider =
    FutureProvider.autoDispose.family<List<ShareLink>, String>((ref, childId) async {
  final data = await ref.watch(apiClientProvider).get('/children/$childId/share-links')
      as List<dynamic>;
  return data
      .map((e) => ShareLink.fromJson(e as Map<String, dynamic>))
      .where((l) => l.isActive)
      .toList(growable: false);
});

final shareActionsProvider = Provider<ShareActions>((ref) {
  return ShareActions(ref);
});

class ShareActions {
  final Ref _ref;
  ShareActions(this._ref);

  /// Create a link and return it (so the caller can show its QR immediately).
  Future<ShareLink> create(String childId, int ttlHours) async {
    final data = await _ref
        .read(apiClientProvider)
        .post('/children/$childId/share-links', body: {'ttl_hours': ttlHours});
    _ref.invalidate(shareLinksProvider(childId));
    return ShareLink.fromJson(data as Map<String, dynamic>);
  }

  Future<void> revoke(String childId, String linkId) async {
    await _ref.read(apiClientProvider).delete('/share-links/$linkId');
    _ref.invalidate(shareLinksProvider(childId));
  }
}
