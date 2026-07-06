/// Runtime configuration. Override at build/run time with:
///   --dart-define=API_BASE_URL=https://api.izylrn.com/v1
class Env {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );
}
