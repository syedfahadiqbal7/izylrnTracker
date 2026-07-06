import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'i18n.dart';
import 'theme.dart';

/// AppBar language picker — switching re-loads the bundle and flips RTL app-wide.
class LanguageButton extends ConsumerWidget {
  const LanguageButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final current = ref.watch(localeControllerProvider);
    final t = ref.watch(translatorProvider);
    final active = supportedLocales.firstWhere((l) => l.code == current,
        orElse: () => supportedLocales.first);

    return PopupMenuButton<String>(
      tooltip: t.t('app.language', 'Language'),
      onSelected: (code) =>
          ref.read(localeControllerProvider.notifier).set(code),
      itemBuilder: (context) => [
        for (final l in supportedLocales)
          PopupMenuItem(
            value: l.code,
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l.nativeName,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      Text(l.name,
                          style: TextStyle(
                              fontSize: 11, color: Colors.grey.shade600)),
                    ],
                  ),
                ),
                if (l.code == current)
                  const Icon(Icons.check, size: 18, color: Brand.cyan),
              ],
            ),
          ),
      ],
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.language, size: 20, color: Brand.ink),
          const SizedBox(width: 4),
          Text(active.code.toUpperCase(),
              style: const TextStyle(
                  fontWeight: FontWeight.w700, color: Brand.ink, fontSize: 13)),
        ]),
      ),
    );
  }
}
