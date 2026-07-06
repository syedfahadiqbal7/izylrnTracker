import '../../core/api_client.dart';
import '../../core/token_store.dart';
import 'user.dart';

class AuthRepository {
  final ApiClient api;
  final TokenStore tokens;
  AuthRepository(this.api, this.tokens);

  /// Request a 6-digit OTP. Returns the delivery channel ("whatsapp"/"sms"/"dev").
  Future<String> sendOtp(String phone) async {
    final data = await api.post('/auth/send-otp', body: {'phone': phone});
    return (data['channel'] ?? 'sms') as String;
  }

  /// Verify the OTP; on success stores the JWT pair. Returns whether the user is new.
  Future<bool> verifyOtp(String phone, String otp) async {
    final data =
        await api.post('/auth/verify-otp', body: {'phone': phone, 'otp': otp});
    await tokens.save(
        data['access_token'] as String, data['refresh_token'] as String);
    return (data['is_new_user'] ?? false) as bool;
  }

  Future<AppUser> me() async {
    final data = await api.get('/auth/me');
    return AppUser.fromJson(data as Map<String, dynamic>);
  }

  Future<void> logout() async {
    final refresh = tokens.refresh;
    try {
      if (refresh != null) {
        await api.delete('/auth/logout', body: {'refresh_token': refresh});
      }
    } catch (_) {
      // best-effort; clear locally regardless
    } finally {
      await tokens.clear();
    }
  }
}
