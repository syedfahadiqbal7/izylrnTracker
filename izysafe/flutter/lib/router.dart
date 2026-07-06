import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/theme.dart';
import 'features/auth/auth_controller.dart';
import 'features/auth/otp_screen.dart';
import 'features/auth/phone_screen.dart';
import 'features/alerts/alerts_screen.dart';
import 'features/children/child.dart';
import 'features/children/home_screen.dart';
import 'features/settings/settings_screen.dart';
import 'features/tracking/live_map_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.onDispose(refresh.dispose);
  ref.listen(authControllerProvider, (_, _) => refresh.value++);

  return GoRouter(
    initialLocation: '/',
    refreshListenable: refresh,
    redirect: (context, state) {
      final auth = ref.read(authControllerProvider);
      final loc = state.matchedLocation;

      if (auth.status == AuthStatus.loading) {
        return loc == '/' ? null : '/';
      }
      final loggedIn = auth.status == AuthStatus.authenticated;
      if (loggedIn) {
        if (loc == '/' || loc == '/login') return '/home';
        return null;
      }
      // not logged in — allow /login and /otp
      if (loc == '/home' || loc == '/') return '/login';
      return null;
    },
    routes: [
      GoRoute(path: '/', builder: (_, _) => const _Splash()),
      GoRoute(path: '/login', builder: (_, _) => const PhoneScreen()),
      GoRoute(
        path: '/otp',
        builder: (_, state) => OtpScreen(
          phone: state.uri.queryParameters['phone'] ?? '',
          channel: state.uri.queryParameters['channel'] ?? 'sms',
        ),
      ),
      GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
      GoRoute(path: '/alerts', builder: (_, _) => const AlertsScreen()),
      GoRoute(path: '/settings', builder: (_, _) => const SettingsScreen()),
      GoRoute(
        path: '/child/:id/map',
        builder: (_, state) => LiveMapScreen(
          childId: state.pathParameters['id']!,
          child: state.extra is Child ? state.extra as Child : null,
        ),
      ),
    ],
  );
});

class _Splash extends StatelessWidget {
  const _Splash();
  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: DecoratedBox(
        decoration: BoxDecoration(gradient: Brand.gradient),
        child: Center(
          child: CircularProgressIndicator(color: Colors.white),
        ),
      ),
    );
  }
}
