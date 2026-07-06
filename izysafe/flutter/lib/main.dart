import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/i18n.dart';
import 'core/theme.dart';
import 'router.dart';

void main() {
  runApp(const ProviderScope(child: IzySafeParentApp()));
}

class IzySafeParentApp extends ConsumerWidget {
  const IzySafeParentApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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
