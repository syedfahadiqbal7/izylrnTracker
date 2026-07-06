import 'package:flutter/material.dart';

import '../../core/i18n.dart';

/// A child's paired GPS device (watch / bag tracker / phone) — the hardware that
/// feeds the Live Map. Mirrors the backend DeviceResponse.
class Device {
  final String id;
  final String name;
  final String deviceType; // watch | bag_tracker | phone
  final String imei;
  final int? traccarId; // null until Traccar registration succeeds (pending seam)
  final String? model;
  final String? color;
  final String? protocol;
  final int batteryThreshold;
  final int watchRemovedThresholdMin;
  final bool watchRemovedEnabled;
  final int? lastBattery;
  final DateTime? lastSeenAt;
  final bool isOnline;
  final bool active;

  const Device({
    required this.id,
    required this.name,
    required this.deviceType,
    required this.imei,
    required this.traccarId,
    required this.model,
    required this.color,
    required this.protocol,
    required this.batteryThreshold,
    required this.watchRemovedThresholdMin,
    required this.watchRemovedEnabled,
    required this.lastBattery,
    required this.lastSeenAt,
    required this.isOnline,
    required this.active,
  });

  /// True once the tracker has connected to Traccar at least once.
  bool get isPending => traccarId == null;

  factory Device.fromJson(Map<String, dynamic> j) => Device(
        id: j['id'] as String,
        name: (j['name'] ?? '') as String,
        deviceType: (j['device_type'] ?? 'watch') as String,
        imei: (j['imei'] ?? '') as String,
        traccarId: (j['traccar_id'] as num?)?.toInt(),
        model: j['model'] as String?,
        color: j['color'] as String?,
        protocol: j['protocol'] as String?,
        batteryThreshold: (j['battery_threshold'] ?? 20) as int,
        watchRemovedThresholdMin: (j['watch_removed_threshold_min'] ?? 10) as int,
        watchRemovedEnabled: (j['watch_removed_enabled'] ?? false) as bool,
        lastBattery: (j['last_battery'] as num?)?.toInt(),
        lastSeenAt: j['last_seen_at'] != null
            ? DateTime.tryParse(j['last_seen_at'] as String)
            : null,
        isOnline: (j['is_online'] ?? false) as bool,
        active: (j['active'] ?? true) as bool,
      );
}

/// Device types the parent can pair (matches the backend DeviceType enum — never 'bus').
const deviceTypes = <String>['watch', 'bag_tracker', 'phone'];

/// Allowed low-battery alert thresholds (matches the DB CHECK).
const batteryThresholds = <int>[10, 15, 20, 30];

/// Allowed watch-removed alert delays in minutes (matches the DB CHECK).
const removedThresholds = <int>[5, 10, 15];

IconData deviceTypeIcon(String dt) {
  switch (dt) {
    case 'bag_tracker':
      return Icons.backpack_rounded;
    case 'phone':
      return Icons.smartphone_rounded;
    default:
      return Icons.watch_rounded;
  }
}

String deviceTypeLabel(Translator t, String dt) {
  switch (dt) {
    case 'bag_tracker':
      return t.t('devices.type_bag_tracker', 'Bag tracker');
    case 'phone':
      return t.t('devices.type_phone', 'Phone');
    default:
      return t.t('devices.type_watch', 'Watch');
  }
}

/// Battery icon reflecting the last-known level (null → unknown).
IconData batteryIcon(int? pct) {
  if (pct == null) return Icons.battery_unknown_rounded;
  if (pct >= 90) return Icons.battery_full_rounded;
  if (pct >= 60) return Icons.battery_5_bar_rounded;
  if (pct >= 35) return Icons.battery_3_bar_rounded;
  if (pct >= 15) return Icons.battery_2_bar_rounded;
  return Icons.battery_alert_rounded;
}
