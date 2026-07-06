import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import 'child.dart';

/// GET /children → the parent's children (via family_members authorization).
final childrenProvider = FutureProvider.autoDispose<List<Child>>((ref) async {
  final api = ref.watch(apiClientProvider);
  final data = await api.get('/children') as List<dynamic>;
  return data
      .map((e) => Child.fromJson(e as Map<String, dynamic>))
      .toList(growable: false);
});
