import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/i18n.dart';
import '../../core/language_button.dart';
import '../../core/theme.dart';
import 'models.dart';
import 'providers.dart';

/// Temporary public live-tracking links for a child — list active links, create a new
/// one (with a QR + copy sheet), and revoke.
class ShareLinksScreen extends ConsumerWidget {
  final String childId;
  final String? childName;
  const ShareLinksScreen({super.key, required this.childId, this.childName});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final links = ref.watch(shareLinksProvider(childId));

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t.t('share.title', 'Share links'),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18)),
            Text(childName ?? t.t('share.subtitle', 'Temporary live-tracking links'),
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
        icon: const Icon(Icons.add_link_rounded),
        label: Text(t.t('share.create', 'Create link')),
        onPressed: () => _startCreate(context, ref),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(shareLinksProvider(childId));
          await ref.read(shareLinksProvider(childId).future);
        },
        child: links.when(
          loading: () =>
              const Center(child: CircularProgressIndicator(strokeWidth: 2.6)),
          error: (e, _) => _Error(
            message: e is ApiException
                ? e.message
                : t.t('alerts.load_error', 'Could not load.'),
            retry: t.t('common.retry', 'Retry'),
            onRetry: () => ref.invalidate(shareLinksProvider(childId)),
          ),
          data: (list) => list.isEmpty
              ? _Empty(
                  title: t.t('share.empty', 'No active links'),
                  hint: t.t('share.empty_hint',
                      "Create a temporary link to let someone follow your child's live location."),
                )
              : ListView(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
                  children: [
                    for (final l in list)
                      _LinkCard(
                        link: l,
                        onTap: () => _showLinkSheet(context, ref, l),
                        onRevoke: () => _confirmRevoke(context, ref, l),
                      ),
                  ],
                ),
        ),
      ),
    );
  }

  // ---- create: pick a duration, create, then show the QR sheet
  Future<void> _startCreate(BuildContext context, WidgetRef ref) async {
    final t = ref.read(translatorProvider);
    final ttl = await showModalBottomSheet<int>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => _DurationPicker(t: t),
    );
    if (ttl == null) return;
    try {
      final link = await ref.read(shareActionsProvider).create(childId, ttl);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(t.t('share.created', 'Share link created'))));
        _showLinkSheet(context, ref, link);
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  void _showLinkSheet(BuildContext context, WidgetRef ref, ShareLink link) {
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (ctx) => _LinkSheet(link: link),
    );
  }

  Future<void> _confirmRevoke(
      BuildContext context, WidgetRef ref, ShareLink link) async {
    final t = ref.read(translatorProvider);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t.t('share.revoke', 'Revoke')),
        content: Text(t.t('share.revoke_confirm',
            'Revoke this link? It will stop working immediately.')),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: Text(t.t('common.cancel', 'Cancel'))),
          FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFE11D48)),
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(t.t('share.revoke', 'Revoke'))),
        ],
      ),
    );
    if (ok == true) {
      try {
        await ref.read(shareActionsProvider).revoke(childId, link.id);
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(t.t('share.revoked', 'Link revoked'))));
        }
      } on ApiException catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    }
  }
}

/// Format a remaining Duration as e.g. "1d 3h" / "5h 12m" / "8m".
String formatRemaining(Translator t, Duration d) {
  if (d <= Duration.zero) return t.t('share.expired', 'Expired');
  final days = d.inDays;
  final hours = d.inHours % 24;
  final mins = d.inMinutes % 60;
  final dL = t.t('share.d_left', 'd');
  final hL = t.t('share.h_left', 'h');
  final mL = t.t('share.m_left', 'm');
  if (days > 0) return '$days$dL $hours$hL';
  if (hours > 0) return '$hours$hL $mins$mL';
  return '$mins$mL';
}

class _LinkCard extends ConsumerWidget {
  final ShareLink link;
  final VoidCallback onTap;
  final VoidCallback onRevoke;
  const _LinkCard(
      {required this.link, required this.onTap, required this.onRevoke});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
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
                  color: Brand.cyan.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Icon(Icons.share_location_rounded,
                    color: Brand.cyan, size: 22),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Icon(Icons.schedule_rounded,
                          size: 14, color: Colors.grey.shade600),
                      const SizedBox(width: 4),
                      Text(
                        '${t.t('share.expires_in', 'Expires in')} ${formatRemaining(t, link.remaining)}',
                        style: const TextStyle(
                            fontWeight: FontWeight.w700, fontSize: 14.5),
                      ),
                    ]),
                    const SizedBox(height: 6),
                    Text(
                      '${link.viewCount} ${t.t('share.views', 'views')}',
                      style: TextStyle(
                          color: Colors.grey.shade600, fontSize: 12.5),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: onRevoke,
                style: TextButton.styleFrom(
                    foregroundColor: const Color(0xFFE11D48)),
                child: Text(t.t('share.revoke', 'Revoke')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DurationPicker extends StatelessWidget {
  final Translator t;
  const _DurationPicker({required this.t});

  String _label(int h) {
    switch (h) {
      case 1:
        return t.t('share.hour_1', '1 hour');
      case 8:
        return t.t('share.hour_8', '8 hours');
      default:
        return t.t('share.hour_24', '24 hours');
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t.t('share.duration', 'Link duration'),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
            const SizedBox(height: 4),
            Text(t.t('share.duration_hint', 'The link stops working after this time.'),
                style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
            const SizedBox(height: 14),
            for (final h in shareTtlHours)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.timer_outlined, color: Brand.indigo),
                title: Text(_label(h),
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pop(context, h),
              ),
          ],
        ),
      ),
    );
  }
}

class _LinkSheet extends ConsumerWidget {
  final ShareLink link;
  const _LinkSheet({required this.link});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(t.t('share.scan', 'Scan to open'),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: const Color(0xFFE6E9F2)),
              ),
              child: QrImageView(
                data: link.url,
                version: QrVersions.auto,
                size: 200,
                eyeStyle: const QrEyeStyle(
                    eyeShape: QrEyeShape.square, color: Brand.ink),
                dataModuleStyle: const QrDataModuleStyle(
                    dataModuleShape: QrDataModuleShape.square, color: Brand.ink),
              ),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: const Color(0xFFEFF2FB),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(children: [
                const Icon(Icons.link_rounded, size: 18, color: Brand.indigo),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(link.url,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12.5, color: Brand.ink)),
                ),
              ]),
            ),
            const SizedBox(height: 8),
            Text(
              '${t.t('share.expires_in', 'Expires in')} ${formatRemaining(t, link.remaining)}',
              style: TextStyle(color: Colors.grey.shade600, fontSize: 12.5),
            ),
            const SizedBox(height: 16),
            Row(children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.copy_rounded, size: 18),
                  label: Text(t.t('share.copy', 'Copy link')),
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: link.url));
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                          content: Text(t.t('share.copied', 'Link copied'))));
                    }
                  },
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(backgroundColor: Brand.indigo),
                  icon: const Icon(Icons.open_in_new_rounded, size: 18),
                  label: Text(t.t('share.open', 'Open')),
                  onPressed: () async {
                    final uri = Uri.tryParse(link.url);
                    if (uri != null) {
                      await launchUrl(uri, mode: LaunchMode.externalApplication);
                    }
                  },
                ),
              ),
            ]),
          ],
        ),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  final String title;
  final String hint;
  const _Empty({required this.title, required this.hint});
  @override
  Widget build(BuildContext context) => ListView(
        children: [
          const SizedBox(height: 100),
          Icon(Icons.share_location_outlined, size: 54, color: Colors.grey.shade400),
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
