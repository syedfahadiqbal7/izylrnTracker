import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/i18n.dart';
import '../../core/language_button.dart';
import '../../core/theme.dart';
import 'models.dart';
import 'providers.dart';

class AlertsScreen extends ConsumerStatefulWidget {
  const AlertsScreen({super.key});
  @override
  ConsumerState<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends ConsumerState<AlertsScreen> {
  bool _unreadOnly = false;

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    final alerts = ref.watch(alertsProvider(_unreadOnly));

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Text(t.t('alerts.title', 'Alerts'),
            style: const TextStyle(fontWeight: FontWeight.w700)),
        actions: [
          const LanguageButton(),
          IconButton(
            tooltip: t.t('alerts.mark_all_read', 'Mark all read'),
            icon: const Icon(Icons.done_all, size: 22),
            onPressed: () => ref.read(alertActionsProvider).markAllRead(),
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Row(
              children: [
                _FilterChip(
                  label: t.t('alerts.all', 'All'),
                  selected: !_unreadOnly,
                  onTap: () => setState(() => _unreadOnly = false),
                ),
                const SizedBox(width: 8),
                _FilterChip(
                  label: t.t('alerts.unread', 'Unread'),
                  selected: _unreadOnly,
                  onTap: () => setState(() => _unreadOnly = true),
                ),
              ],
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                ref.invalidate(alertsProvider(_unreadOnly));
                await ref.read(alertsProvider(_unreadOnly).future);
              },
              child: alerts.when(
                loading: () => const Center(
                    child: CircularProgressIndicator(strokeWidth: 2.6)),
                error: (e, _) => _ErrorState(
                  message: e is ApiException
                      ? e.message
                      : t.t('alerts.load_error', 'Could not load alerts.'),
                  retryLabel: t.t('common.retry', 'Retry'),
                  onRetry: () => ref.invalidate(alertsProvider(_unreadOnly)),
                ),
                data: (result) => result.items.isEmpty
                    ? _EmptyState(
                        title: t.t('alerts.empty', "You're all caught up"),
                        hint: t.t('alerts.empty_hint',
                            'New alerts about your children will appear here.'),
                      )
                    : ListView.separated(
                        padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
                        itemCount: result.items.length,
                        separatorBuilder: (_, _) => const SizedBox(height: 8),
                        itemBuilder: (_, i) =>
                            _AlertTile(alert: result.items[i]),
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AlertTile extends ConsumerWidget {
  final AppAlert alert;
  const _AlertTile({required this.alert});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final visual = _visualFor(alert.type);
    final title = alert.title ?? t.t('alert_type.${alert.type}', visual.fallback);

    return Material(
      color: alert.read ? Colors.white : const Color(0xFFF3F6FF),
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () async {
          if (!alert.read) {
            await ref.read(alertActionsProvider).markRead(alert.id);
          }
          if (alert.hasLocation && context.mounted) {
            context.push('/child/${alert.childId}/map');
          }
        },
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                radius: 20,
                backgroundColor: visual.color.withValues(alpha: 0.12),
                child: Icon(visual.icon, color: visual.color, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(title,
                              style: TextStyle(
                                  fontWeight: alert.read
                                      ? FontWeight.w600
                                      : FontWeight.w700,
                                  fontSize: 15)),
                        ),
                        if (!alert.read)
                          Container(
                            width: 9,
                            height: 9,
                            margin: const EdgeInsets.only(left: 6, top: 4),
                            decoration: const BoxDecoration(
                                color: Brand.indigo, shape: BoxShape.circle),
                          ),
                      ],
                    ),
                    if (alert.body != null) ...[
                      const SizedBox(height: 3),
                      Text(alert.body!,
                          style: TextStyle(
                              color: Colors.grey.shade700, fontSize: 13)),
                    ],
                    const SizedBox(height: 6),
                    Row(children: [
                      Text(_ago(alert.createdAt, t),
                          style: TextStyle(
                              color: Colors.grey.shade500, fontSize: 11.5)),
                      if (alert.hasLocation) ...[
                        const SizedBox(width: 10),
                        Icon(Icons.place, size: 12, color: Brand.cyan),
                        const SizedBox(width: 2),
                        Text(t.t('alerts.view_on_map', 'View on map'),
                            style: const TextStyle(
                                color: Brand.cyan,
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600)),
                      ],
                    ]),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _FilterChip(
      {required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? Brand.indigo : Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
              color: selected ? Brand.indigo : const Color(0xFFE2E6F0)),
        ),
        child: Text(label,
            style: TextStyle(
                color: selected ? Colors.white : Brand.ink,
                fontWeight: FontWeight.w600,
                fontSize: 13)),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final String title;
  final String hint;
  const _EmptyState({required this.title, required this.hint});
  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 100),
        Icon(Icons.notifications_none, size: 52, color: Colors.grey.shade400),
        const SizedBox(height: 14),
        Center(
            child: Text(title,
                style: const TextStyle(
                    fontWeight: FontWeight.w700, fontSize: 16))),
        const SizedBox(height: 6),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 40),
          child: Text(hint,
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey.shade600)),
        ),
      ],
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final String retryLabel;
  final VoidCallback onRetry;
  const _ErrorState(
      {required this.message,
      required this.retryLabel,
      required this.onRetry});
  @override
  Widget build(BuildContext context) {
    return ListView(children: [
      const SizedBox(height: 120),
      Icon(Icons.cloud_off, size: 44, color: Colors.grey.shade400),
      const SizedBox(height: 12),
      Center(
          child: Text(message,
              style: const TextStyle(
                  color: Colors.red, fontWeight: FontWeight.w500))),
      const SizedBox(height: 12),
      Center(child: OutlinedButton(onPressed: onRetry, child: Text(retryLabel))),
    ]);
  }
}

class _Visual {
  final IconData icon;
  final Color color;
  final String fallback;
  const _Visual(this.icon, this.color, this.fallback);
}

_Visual _visualFor(String type) {
  switch (type) {
    case 'sos':
    case 'crash':
      return const _Visual(Icons.crisis_alert, Color(0xFFE11D48), 'SOS Emergency');
    case 'geofence_enter':
    case 'geofence_exit':
      return const _Visual(Icons.shield_outlined, Brand.indigo, 'Safe-zone alert');
    case 'school_arrival':
    case 'school_absent':
      return const _Visual(Icons.school, Brand.cyan, 'School attendance');
    case 'low_battery':
    case 'critical_battery':
      return const _Visual(Icons.battery_alert, Color(0xFFF59E0B), 'Low battery');
    case 'speed':
    case 'route_deviation':
      return const _Visual(Icons.speed, Color(0xFFF59E0B), 'Speed alert');
    case 'device_offline':
    case 'watch_removed':
      return const _Visual(Icons.cloud_off, Colors.grey, 'Tracker offline');
    case 'bus_arrival':
    case 'bus_boarded':
    case 'pickup':
      return const _Visual(Icons.directions_bus, Brand.cyan, 'Bus update');
    default:
      return const _Visual(Icons.notifications, Brand.violet, 'Notification');
  }
}

String _ago(DateTime ts, Translator t) {
  final d = DateTime.now().difference(ts);
  if (d.inMinutes < 1) return t.t('map.moments_ago', 'moments ago');
  if (d.inMinutes < 60) return '${d.inMinutes} ${t.t('map.min_ago', 'min ago')}';
  if (d.inHours < 24) return '${d.inHours} ${t.t('map.hr_ago', 'hr ago')}';
  return '${d.inDays}d';
}
