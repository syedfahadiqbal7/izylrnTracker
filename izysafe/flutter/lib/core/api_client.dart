import 'package:dio/dio.dart';

import 'env.dart';
import 'token_store.dart';

/// Thrown for any non-2xx response, carrying the backend error `code`.
class ApiException implements Exception {
  final int status;
  final String code;
  final String message;
  ApiException(this.status, this.code, this.message);
  @override
  String toString() => 'ApiException($status, $code): $message';
}

/// Dio client for the IzySafe backend.
///
/// - Attaches the parent access token to every request.
/// - On a 401 it refreshes once via POST /auth/refresh (single-flight), rotating
///   both tokens, and retries the original request.
/// - On refresh failure it clears the session and invokes [onForcedLogout].
/// - Normalizes the backend envelope ({data} / {error,code,message}).
class ApiClient {
  final TokenStore tokens;
  void Function()? onForcedLogout;

  late final Dio _dio;
  // Bare client for the refresh call — must not recurse through the interceptor.
  late final Dio _refreshDio;
  Future<String>? _refreshing;

  ApiClient(this.tokens) {
    final options = BaseOptions(
      baseUrl: Env.apiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 20),
      headers: {'Content-Type': 'application/json'},
    );
    _dio = Dio(options);
    _refreshDio = Dio(options);

    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (req, handler) {
        final token = tokens.access;
        if (token != null) req.headers['Authorization'] = 'Bearer $token';
        handler.next(req);
      },
      onError: (err, handler) async {
        final req = err.requestOptions;
        final isAuthPath = req.path.contains('/auth/refresh') ||
            req.path.contains('/auth/verify-otp') ||
            req.path.contains('/auth/send-otp');
        if (err.response?.statusCode == 401 &&
            req.extra['retried'] != true &&
            !isAuthPath &&
            tokens.refresh != null) {
          try {
            final newAccess = await _refresh();
            req.extra['retried'] = true;
            req.headers['Authorization'] = 'Bearer $newAccess';
            final clone = await _dio.fetch(req);
            return handler.resolve(clone);
          } catch (_) {
            await tokens.clear();
            onForcedLogout?.call();
          }
        }
        handler.next(err);
      },
    ));
  }

  Future<String> _refresh() {
    return _refreshing ??= () async {
      try {
        final resp = await _refreshDio.post('/auth/refresh',
            data: {'refresh_token': tokens.refresh});
        final data = resp.data['data'] as Map<String, dynamic>;
        await tokens.save(
            data['access_token'] as String, data['refresh_token'] as String);
        return data['access_token'] as String;
      } finally {
        _refreshing = null;
      }
    }();
  }

  // ------------------------------------------------------------- typed helpers
  Future<dynamic> get(String path, {Map<String, dynamic>? query}) =>
      _unwrap(() => _dio.get(path, queryParameters: query));

  Future<dynamic> post(String path, {Object? body}) =>
      _unwrap(() => _dio.post(path, data: body));

  Future<dynamic> put(String path, {Object? body}) =>
      _unwrap(() => _dio.put(path, data: body));

  Future<dynamic> delete(String path, {Object? body}) =>
      _unwrap(() => _dio.delete(path, data: body));

  Future<dynamic> _unwrap(Future<Response> Function() call) async {
    try {
      final resp = await call();
      final body = resp.data;
      if (body is Map && body.containsKey('data')) return body['data'];
      return body;
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  ApiException _toApiException(DioException e) {
    final status = e.response?.statusCode ?? 0;
    final body = e.response?.data;
    if (body is Map && body['code'] != null) {
      return ApiException(
          status, body['code'] as String, (body['message'] ?? '') as String);
    }
    if (status == 0) {
      return ApiException(0, 'NETWORK_ERROR', 'Could not reach the server');
    }
    return ApiException(status, 'HTTP_$status', e.message ?? 'Request failed');
  }
}
