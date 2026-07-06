import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../features/auth/auth_controller.dart';

/// Supported UI languages — mirrors the backend `translations` columns + LOCALE_META.
class AppLocale {
  final String code;
  final String name;
  final String nativeName;
  final bool rtl;
  const AppLocale(this.code, this.name, this.nativeName, {this.rtl = false});
}

const supportedLocales = <AppLocale>[
  AppLocale('en', 'English', 'English'),
  AppLocale('hi', 'Hindi', 'हिन्दी'),
  AppLocale('ar', 'Arabic', 'العربية', rtl: true),
];

const _localeKey = 'izylrn.locale';

/// Holds the active locale, persisted in secure storage (same store as the tokens).
class LocaleController extends StateNotifier<String> {
  final FlutterSecureStorage _storage;
  LocaleController(this._storage) : super('en') {
    _load();
  }

  Future<void> _load() async {
    final saved = await _storage.read(key: _localeKey);
    if (saved != null && supportedLocales.any((l) => l.code == saved)) {
      state = saved;
    }
  }

  Future<void> set(String code) async {
    state = code;
    await _storage.write(key: _localeKey, value: code);
  }
}

final localeControllerProvider =
    StateNotifierProvider<LocaleController, String>((ref) {
  return LocaleController(const FlutterSecureStorage());
});

/// Loads the {key: value} bundle for a locale from GET /i18n/{locale} (English-fallback
/// filled server-side). Public endpoint — works before login.
final translationsProvider =
    FutureProvider.family<Map<String, String>, String>((ref, locale) async {
  final data = await ref.watch(apiClientProvider).get('/i18n/$locale');
  return (data as Map).map((k, v) => MapEntry(k as String, '$v'));
});

/// Translate keys against the active locale's bundle. While the bundle loads it returns
/// the supplied fallback (or the key), so the UI never flashes a raw key.
class Translator {
  final String locale;
  final Map<String, String> _m;
  const Translator(this.locale, this._m);

  String t(String key, [String? fallback]) => _m[key] ?? fallback ?? key;

  bool get isRTL => supportedLocales.firstWhere((l) => l.code == locale,
      orElse: () => supportedLocales.first).rtl;

  TextDirection get direction =>
      isRTL ? TextDirection.rtl : TextDirection.ltr;
}

/// The current [Translator]. Rebuilds when the locale changes or its bundle arrives.
final translatorProvider = Provider<Translator>((ref) {
  final locale = ref.watch(localeControllerProvider);
  final bundle = ref.watch(translationsProvider(locale)).valueOrNull ?? const {};
  return Translator(locale, bundle);
});
