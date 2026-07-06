import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Persists the parent JWT pair (access 24h / refresh 30d) in secure storage.
class TokenStore {
  static const _access = 'izysafe.access_token';
  static const _refresh = 'izysafe.refresh_token';

  final FlutterSecureStorage _storage;
  TokenStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  // In-memory mirror so the request interceptor stays synchronous and fast.
  String? _accessCache;
  String? _refreshCache;

  Future<void> load() async {
    _accessCache = await _storage.read(key: _access);
    _refreshCache = await _storage.read(key: _refresh);
  }

  String? get access => _accessCache;
  String? get refresh => _refreshCache;
  bool get hasSession => _accessCache != null;

  Future<void> save(String access, String refresh) async {
    _accessCache = access;
    _refreshCache = refresh;
    await _storage.write(key: _access, value: access);
    await _storage.write(key: _refresh, value: refresh);
  }

  Future<void> clear() async {
    _accessCache = null;
    _refreshCache = null;
    await _storage.delete(key: _access);
    await _storage.delete(key: _refresh);
  }
}
