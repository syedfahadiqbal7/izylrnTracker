class AppUser {
  final String id;
  final String phone;
  final String? name;
  final String? email;
  final String? photoUrl;
  final String countryCode;
  final String language;
  final String timezone;
  final String subscriptionTier;

  AppUser({
    required this.id,
    required this.phone,
    required this.name,
    required this.email,
    required this.photoUrl,
    required this.countryCode,
    required this.language,
    required this.timezone,
    required this.subscriptionTier,
  });

  factory AppUser.fromJson(Map<String, dynamic> j) => AppUser(
        id: j['id'] as String,
        phone: j['phone'] as String,
        name: j['name'] as String?,
        email: j['email'] as String?,
        photoUrl: j['photo_url'] as String?,
        countryCode: j['country_code'] as String,
        language: j['language'] as String,
        timezone: j['timezone'] as String,
        subscriptionTier: j['subscription_tier'] as String,
      );

  String get displayName => (name != null && name!.isNotEmpty) ? name! : phone;
}
