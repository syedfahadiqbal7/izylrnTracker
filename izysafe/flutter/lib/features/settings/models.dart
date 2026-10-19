/// The parent's profile + notification prefs (GET /auth/me).
class Contact {
  final String label;
  final String phone;
  const Contact({required this.label, required this.phone});

  factory Contact.fromJson(Map<String, dynamic> j) =>
      Contact(label: (j['label'] ?? '') as String, phone: (j['phone'] ?? '') as String);

  Map<String, String> toJson() => {'label': label, 'phone': phone};
}

class ProfileSettings {
  final String id;
  final String phone;
  final String? name;
  final String? email;
  final String? photoUrl;
  final String language;
  final String tier;
  final String? quietFrom; // "HH:MM" or null
  final String? quietTo;
  final String? address;
  final double? homeLat;
  final double? homeLng;
  final List<Contact> additionalContacts;

  const ProfileSettings({
    required this.id,
    required this.phone,
    required this.name,
    required this.email,
    required this.photoUrl,
    required this.language,
    required this.tier,
    required this.quietFrom,
    required this.quietTo,
    this.address,
    this.homeLat,
    this.homeLng,
    this.additionalContacts = const [],
  });

  bool get quietHoursOn => quietFrom != null && quietTo != null;

  factory ProfileSettings.fromJson(Map<String, dynamic> j) => ProfileSettings(
        id: j['id'] as String,
        phone: j['phone'] as String,
        name: j['name'] as String?,
        email: j['email'] as String?,
        photoUrl: j['photo_url'] as String?,
        language: (j['language'] ?? 'en') as String,
        tier: (j['subscription_tier'] ?? 'free') as String,
        quietFrom: _hhmm(j['quiet_hours_from']),
        quietTo: _hhmm(j['quiet_hours_to']),
        address: j['address'] as String?,
        homeLat: (j['home_lat'] as num?)?.toDouble(),
        homeLng: (j['home_lng'] as num?)?.toDouble(),
        additionalContacts: ((j['additional_contacts'] ?? []) as List)
            .map((e) => Contact.fromJson(e as Map<String, dynamic>))
            .toList(growable: false),
      );

  String get displayName =>
      (name != null && name!.isNotEmpty) ? name! : phone;

  String get initials {
    final base = (name != null && name!.trim().isNotEmpty) ? name!.trim() : phone;
    final parts = base.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts.last.substring(0, 1)).toUpperCase();
  }
}

/// The parent's current plan (GET /subscriptions/me).
class SubscriptionInfo {
  final String tier; // free | basic | premium
  final String status; // active | past_due | cancelled | expired | free
  final bool isActivePaid;
  final DateTime? periodEnd;

  const SubscriptionInfo({
    required this.tier,
    required this.status,
    required this.isActivePaid,
    required this.periodEnd,
  });

  factory SubscriptionInfo.fromJson(Map<String, dynamic> j) => SubscriptionInfo(
        tier: (j['tier'] ?? 'free') as String,
        status: (j['status'] ?? 'free') as String,
        isActivePaid: (j['is_active_paid'] ?? false) as bool,
        periodEnd: j['current_period_end'] != null
            ? DateTime.tryParse('${j['current_period_end']}')?.toLocal()
            : null,
      );
}

/// A sellable plan from the catalog (GET /subscriptions/plans).
class Plan {
  final String tier;
  final String name;
  final String currency; // INR | AED
  final int? price; // monthly, major units; null = custom (contact sales)
  final bool purchasable;
  final List<String> features;

  const Plan({
    required this.tier,
    required this.name,
    required this.currency,
    required this.price,
    required this.purchasable,
    required this.features,
  });

  factory Plan.fromJson(Map<String, dynamic> j) => Plan(
        tier: j['tier'] as String,
        name: j['name'] as String,
        currency: (j['currency'] ?? 'INR') as String,
        price: (j['price'] as num?)?.toInt(),
        purchasable: (j['purchasable'] ?? false) as bool,
        features: ((j['features'] ?? []) as List).map((e) => e as String).toList(),
      );

  String get symbol => currency == 'AED' ? 'AED ' : '₹';
  String get priceLabel => price == null
      ? ''
      : price == 0
          ? ''
          : '$symbol$price';
}

/// A Premium emergency contact (per child).
class EmergencyContact {
  final String id;
  final String childId;
  final String childName;
  final String name;
  final String phone;
  final String? relationship;

  const EmergencyContact({
    required this.id,
    required this.childId,
    required this.childName,
    required this.name,
    required this.phone,
    required this.relationship,
  });

  factory EmergencyContact.fromJson(Map<String, dynamic> j, String childName) =>
      EmergencyContact(
        id: j['id'] as String,
        childId: j['child_id'] as String,
        childName: childName,
        name: j['name'] as String,
        phone: j['phone'] as String,
        relationship: j['relationship'] as String?,
      );
}

/// Time fields arrive as "HH:MM:SS" (or "HH:MM"); keep just "HH:MM".
String? _hhmm(dynamic v) {
  if (v == null) return null;
  final s = '$v';
  return s.length >= 5 ? s.substring(0, 5) : s;
}
