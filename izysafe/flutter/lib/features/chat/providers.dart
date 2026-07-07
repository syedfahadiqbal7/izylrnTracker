import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../alerts/providers.dart' as alerts;
import '../auth/auth_controller.dart';
import 'models.dart';

/// Chat history for a child, polled every few seconds for near-real-time updates
/// (the backend has no socket). Returns oldest→newest (the API is most-recent-first).
///
/// The first fetch surfaces its error to the UI; later poll failures are swallowed so a
/// transient blip doesn't blank an open conversation.
final chatMessagesProvider =
    StreamProvider.autoDispose.family<List<ChatMessage>, String>((ref, childId) async* {
  final api = ref.watch(apiClientProvider);
  List<ChatMessage>? last;
  while (true) {
    try {
      final data = await api.get('/children/$childId/chat', query: {'limit': '100'})
          as List<dynamic>;
      last = data
          .map((e) => ChatMessage.fromJson(e as Map<String, dynamic>))
          .toList()
          .reversed
          .toList(growable: false);
      yield last;
    } catch (e) {
      if (last == null) rethrow; // first load failed → let the UI show the error
    }
    await Future<void>.delayed(const Duration(seconds: 6));
  }
});

final chatActionsProvider = Provider<ChatActions>((ref) {
  return ChatActions(ref);
});

class ChatActions {
  final Ref _ref;
  ChatActions(this._ref);

  /// Send a parent→watch message, then refresh the thread immediately.
  Future<void> send(String childId, String content) async {
    await _ref.read(apiClientProvider).post(
      '/children/$childId/chat',
      body: {'content': content},
    );
    _ref.invalidate(chatMessagesProvider(childId)); // re-poll now
    _ref.invalidate(alerts.unreadCountProvider); // an inbound reply may have arrived
  }
}
