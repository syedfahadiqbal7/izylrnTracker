import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/token_store.dart';
import 'auth_repository.dart';
import 'user.dart';

enum AuthStatus { loading, unauthenticated, authenticated }

@immutable
class AuthState {
  final AuthStatus status;
  final AppUser? user;
  const AuthState(this.status, [this.user]);
}

// ---- providers -------------------------------------------------------------
final tokenStoreProvider = Provider<TokenStore>((ref) => TokenStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(ref.watch(tokenStoreProvider));
});

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(
      ref.watch(apiClientProvider), ref.watch(tokenStoreProvider));
});

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>((ref) {
  return AuthController(ref);
});

class AuthController extends StateNotifier<AuthState> {
  final Ref ref;
  AuthController(this.ref) : super(const AuthState(AuthStatus.loading)) {
    // A refresh failure in the API layer forces the session closed.
    ref.read(apiClientProvider).onForcedLogout = () {
      if (mounted) state = const AuthState(AuthStatus.unauthenticated);
    };
    _bootstrap();
  }

  TokenStore get _tokens => ref.read(tokenStoreProvider);
  AuthRepository get _repo => ref.read(authRepositoryProvider);

  Future<void> _bootstrap() async {
    await _tokens.load();
    if (!_tokens.hasSession) {
      state = const AuthState(AuthStatus.unauthenticated);
      return;
    }
    await loadUser();
  }

  /// After a successful OTP verify (tokens already stored), resolve the user.
  Future<void> loadUser() async {
    try {
      final user = await _repo.me();
      state = AuthState(AuthStatus.authenticated, user);
    } catch (_) {
      await _tokens.clear();
      state = const AuthState(AuthStatus.unauthenticated);
    }
  }

  Future<void> logout() async {
    await _repo.logout();
    state = const AuthState(AuthStatus.unauthenticated);
  }
}
