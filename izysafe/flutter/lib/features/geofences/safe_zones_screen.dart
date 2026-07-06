import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/i18n.dart';
import '../../core/language_button.dart';
import '../../core/theme.dart';
import 'models.dart';
import 'providers.dart';
import 'zone_editor_screen.dart';

class SafeZonesScreen extends ConsumerWidget {
  final String childId;
  final String? childName;
  const SafeZonesScreen({super.key, required this.childId, this.childName});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final zones = ref.watch(safeZonesProvider(childId));

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t.t('zones.title', 'Safe zones'),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18)),
            if (childName != null)
              Text(childName!,
                  style: TextStyle(
                      fontWeight: FontWeight.w500,
                      fontSize: 12.5,
                      color: Colors.grey.shade600)),
          ],
        ),
        actions: const [LanguageButton(), SizedBox(width: 4)],
      ),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: Brand.indigo,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add_location_alt),
        label: Text(t.t('zones.add', 'Add zone')),
        onPressed: () => _openEditor(context, ref),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(safeZonesProvider(childId));
          await ref.read(safeZonesProvider(childId).future);
        },
        child: zones.when(
          loading: () =>
              const Center(child: CircularProgressIndicator(strokeWidth: 2.6)),
          error: (e, _) => _Error(
            message: e is ApiException
                ? e.message
                : t.t('alerts.load_error', 'Could not load.'),
            retry: t.t('common.retry', 'Retry'),
            onRetry: () => ref.invalidate(safeZonesProvider(childId)),
          ),
          data: (list) => list.isEmpty
              ? _Empty(
                  title: t.t('zones.empty', 'No safe zones yet'),
                  hint: t.t('zones.empty_hint',
                      'Add a zone to get alerts when your child enters or leaves.'),
                )
              : ListView(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
                  children: [
                    for (final z in list)
                      _ZoneCard(
                        zone: z,
                        onTap: () => _openEditor(context, ref, zone: z),
                        onDelete: () => _confirmDelete(context, ref, z),
                      ),
                  ],
                ),
        ),
      ),
    );
  }

  void _openEditor(BuildContext context, WidgetRef ref, {SafeZone? zone}) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ZoneEditorScreen(
          childId: childId, childName: childName, existing: zone),
    ));
  }

  Future<void> _confirmDelete(
      BuildContext context, WidgetRef ref, SafeZone z) async {
    final t = ref.read(translatorProvider);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t.t('common.delete', 'Delete')),
        content: Text(
            '${t.t('zones.delete_confirm', 'Delete this safe zone?')}\n\n${z.name}'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: Text(t.t('common.cancel', 'Cancel'))),
          FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFE11D48)),
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(t.t('common.delete', 'Delete'))),
        ],
      ),
    );
    if (ok == true) {
      try {
        await ref.read(geofenceActionsProvider).delete(childId, z.id);
      } on ApiException catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    }
  }
}

class _ZoneCard extends ConsumerWidget {
  final SafeZone zone;
  final VoidCallback onTap;
  final VoidCallback onDelete;
  const _ZoneCard(
      {required this.zone, required this.onTap, required this.onDelete});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final subtitle = zone.isCircle
        ? '${t.t('zones.circle', 'Circle')} · ${zone.radiusM} m'
        : '${t.t('zones.polygon', 'Polygon')} · ${zone.polygon.length} ${t.t('zones.points', 'points')}';

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Container(
                height: 46,
                width: 46,
                decoration: BoxDecoration(
                  color: zone.colorValue.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(zoneTypeIcon(zone.zoneType),
                    color: zone.colorValue, size: 22),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Flexible(
                        child: Text(zone.name,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 15.5)),
                      ),
                      if (!zone.active) ...[
                        const SizedBox(width: 8),
                        _tag(t.t('zones.paused', 'Paused'), Colors.grey),
                      ],
                    ]),
                    const SizedBox(height: 2),
                    Text(subtitle,
                        style: TextStyle(
                            color: Colors.grey.shade600, fontSize: 12.5)),
                    const SizedBox(height: 8),
                    Row(children: [
                      if (zone.notifyEnter)
                        _tag(t.t('zones.enter', 'Enter'), Brand.indigo),
                      if (zone.notifyEnter && zone.notifyExit)
                        const SizedBox(width: 6),
                      if (zone.notifyExit)
                        _tag(t.t('zones.exit', 'Exit'), Brand.violet),
                      if (!zone.notifyEnter && !zone.notifyExit)
                        _tag(t.t('zones.muted', 'Muted'), Colors.grey),
                    ]),
                  ],
                ),
              ),
              PopupMenuButton<String>(
                onSelected: (v) {
                  if (v == 'edit') onTap();
                  if (v == 'delete') onDelete();
                },
                itemBuilder: (_) => [
                  PopupMenuItem(value: 'edit', child: Text(t.t('common.edit', 'Edit'))),
                  PopupMenuItem(
                      value: 'delete', child: Text(t.t('common.delete', 'Delete'))),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _tag(String label, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(7),
        ),
        child: Text(label,
            style: TextStyle(
                color: color, fontSize: 11, fontWeight: FontWeight.w600)),
      );
}

class _Empty extends StatelessWidget {
  final String title;
  final String hint;
  const _Empty({required this.title, required this.hint});
  @override
  Widget build(BuildContext context) => ListView(
        children: [
          const SizedBox(height: 100),
          Icon(Icons.shield_outlined, size: 54, color: Colors.grey.shade400),
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

class _Error extends StatelessWidget {
  final String message;
  final String retry;
  final VoidCallback onRetry;
  const _Error(
      {required this.message, required this.retry, required this.onRetry});
  @override
  Widget build(BuildContext context) => ListView(children: [
        const SizedBox(height: 120),
        Icon(Icons.cloud_off, size: 44, color: Colors.grey.shade400),
        const SizedBox(height: 12),
        Center(
            child: Text(message,
                style: const TextStyle(
                    color: Colors.red, fontWeight: FontWeight.w500))),
        const SizedBox(height: 12),
        Center(child: OutlinedButton(onPressed: onRetry, child: Text(retry))),
      ]);
}
