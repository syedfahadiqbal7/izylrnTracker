/// A temporary public live-tracking link for a child (mirrors backend ShareLinkResponse).
class ShareLink {
  final String id;
  final String token;
  final String url;
  final DateTime expiresAt;
  final int viewCount;
  final bool revoked;
  final DateTime createdAt;

  const ShareLink({
    required this.id,
    required this.token,
    required this.url,
    required this.expiresAt,
    required this.viewCount,
    required this.revoked,
    required this.createdAt,
  });

  bool get isExpired => !expiresAt.isAfter(DateTime.now().toUtc());
  bool get isActive => !revoked && !isExpired;

  /// Time left until expiry (zero if already expired).
  Duration get remaining {
    final d = expiresAt.difference(DateTime.now().toUtc());
    return d.isNegative ? Duration.zero : d;
  }

  factory ShareLink.fromJson(Map<String, dynamic> j) => ShareLink(
        id: j['id'] as String,
        token: (j['token'] ?? '') as String,
        url: (j['url'] ?? '') as String,
        expiresAt: DateTime.parse(j['expires_at'] as String).toUtc(),
        viewCount: (j['view_count'] ?? 0) as int,
        revoked: (j['revoked'] ?? false) as bool,
        createdAt: DateTime.parse(j['created_at'] as String).toUtc(),
      );
}

/// The validity durations the backend accepts (ALLOWED_TTL_HOURS).
const shareTtlHours = <int>[1, 8, 24];
