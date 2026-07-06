import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/i18n.dart';
import 'core/push.dart';
import 'core/theme.dart';
import 'router.dart';

void main() {
  runApp(const ProviderScope(child: IzySafeParentApp()));
}

class IzySafeParentApp extends ConsumerStatefulWidget {
  const IzySafeParentApp({super.key});

  @override
  ConsumerState<IzySafeParentApp> createState() => _IzySafeParentAppState();
}

class _IzySafeParentAppState extends ConsumerState<IzySafeParentApp> {
  @override
  void initState() {
    super.initState();
    // Wire up FCM (no-op until Firebase config ships) + notification deep-linking.
    ref.read(pushServiceProvider).init();
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    final direction = ref.watch(translatorProvider).direction;
    return MaterialApp.router(
      title: 'izyLrn',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      routerConfig: router,
      // Flip the whole app to RTL for Arabic.
      builder: (context, child) =>
          Directionality(textDirection: direction, child: child!),
    );
  }
}
