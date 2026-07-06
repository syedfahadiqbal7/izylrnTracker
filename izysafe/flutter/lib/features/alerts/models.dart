/// A notification-inbox row (SOS, geofence, battery, speed, device-offline, …).
/// `data` carries the deep-link payload the notification/tap routes on.
class AppAlert {
  final String id;
  final String? childId;
  final String type;
  final String? title;
  final String? body;
  final Map<String, dynamic> data;
  final bool read;
  final DateTime createdAt;

  const AppAlert({
    required this.id,
    required this.childId,
    required this.type,
    required this.title,
    required this.body,
    required this.data,
    required this.read,
    required this.createdAt,
  });

  /// Does this alert deep-link to a child's live map?
  bool get hasLocation => childId != null;

  factory AppAlert.fromJson(Map<String, dynamic> j) => AppAlert(
        id: j['id'] as String,
        childId: j['child_id'] as String?,
        type: (j['type'] ?? 'system') as String,
        title: j['title'] as String?,
        body: j['body'] as String?,
        data: (j['data'] as Map?)?.cast<String, dynamic>() ?? const {},
        read: (j['read'] ?? false) as bool,
        createdAt:
            DateTime.tryParse('${j['created_at']}')?.toLocal() ?? DateTime(2000),
      );
}

/// A page of alerts plus the inbox-wide unread badge count (from the list `meta`).
class AlertsResult {
  final List<AppAlert> items;
  final int unreadCount;
  const AlertsResult(this.items, this.unreadCount);
}
