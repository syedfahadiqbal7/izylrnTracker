import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/auth/auth_controller.dart';
import '../router.dart';

/// Push notifications (FCM) + notification deep-linking.
///
/// Actually *receiving* FCM needs firebase_core + firebase_messaging + platform config
/// (google-services.json / GoogleService-Info.plist / web Firebase config) — pending,
/// exactly like the RTDB live stream. Until then [init] is a no-op; the deep-link routing
/// ([routeForData]) and the token registration ([registerToken]) are real and drop straight
/// into the firebase_messaging callbacks once configured (see the TODO in [init]).
class PushService {
  final Ref _ref;
  PushService(this._ref);

  Future<void> init() async {
    // TODO(firebase): once FCM config ships —
    //   final m = FirebaseMessaging.instance;
    //   await m.requestPermission();
    //   final token = await m.getToken();
    //   if (token != null) await registerToken(token);
    //   m.onTokenRefresh.listen(registerToken);
    //   FirebaseMessaging.onMessageOpenedApp.listen((msg) => handleTap(msg.data));
    //   final initial = await m.getInitialMessage();
    //   if (initial != null) handleTap(initial.data);
  }

  /// Register/refresh this device's FCM token so the backend can target pushes at it.
  Future<void> registerToken(String token) async {
    try {
      await _ref
          .read(apiClientProvider)
          .put('/auth/me/fcm-token', body: {'fcm_token': token});
    } catch (_) {
      // best-effort — a failed registration must never block the app
    }
  }

  /// Route a tapped notification to the right screen.
  void handleTap(Map<String, dynamic> data) {
    final loc = routeForData(data);
    if (loc != null) _ref.read(routerProvider).go(loc);
  }

  /// Pure mapping from an alert/notification payload to a route (the deep link).
  /// Any child-scoped alert (SOS, geofence, arrival, …) opens that child's live map;
  /// everything else opens the alerts inbox.
  static String? routeForData(Map<String, dynamic> data) {
    final childId = data['child_id']?.toString();
    if (childId != null && childId.isNotEmpty) return '/child/$childId/map';
    return '/alerts';
  }
}

final pushServiceProvider = Provider<PushService>((ref) => PushService(ref));
