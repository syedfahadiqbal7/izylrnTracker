import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/i18n.dart';
import '../../core/language_button.dart';
import '../../core/theme.dart';
import '../alerts/providers.dart';
import '../auth/auth_controller.dart';
import 'child.dart';
import 'children_providers.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final children = ref.watch(childrenProvider);
    final user = ref.watch(authControllerProvider).user;
    final t = ref.watch(translatorProvider);

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Row(
          children: [
            Image.asset('assets/images/izylrn-icon.png', height: 26),
            const SizedBox(width: 8),
            Text.rich(TextSpan(children: const [
              TextSpan(
                  text: 'izy',
                  style: TextStyle(
                      fontWeight: FontWeight.w800, color: Brand.ink)),
              TextSpan(
                  text: 'Lrn',
                  style: TextStyle(
                      fontWeight: FontWeight.w800, color: Brand.cyan)),
            ])),
          ],
        ),
        actions: [
          const _AlertsBell(),
          const LanguageButton(),
          IconButton(
            tooltip: t.t('nav.settings', 'Settings'),
            icon: const Icon(Icons.settings_outlined, size: 22),
            onPressed: () => context.push('/settings'),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(childrenProvider);
          await ref.read(childrenProvider.future);
        },
        child: children.when(
          loading: () =>
              const Center(child: CircularProgressIndicator(strokeWidth: 2.6)),
          error: (e, _) => _ErrorState(
            message: e is ApiException ? e.message : 'Could not load children',
            retryLabel: t.t('common.retry', 'Retry'),
            onRetry: () => ref.invalidate(childrenProvider),
          ),
          data: (list) => ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 8, 4, 4),
                child: Text('${t.t('app.hi', 'Hi')} ${user?.displayName ?? ''} 👋',
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w700)),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
                child: Text(
                    list.isEmpty
                        ? t.t('home.no_children', 'No children yet')
                        : '${list.length} ${list.length == 1 ? t.t('home.child', 'child') : t.t('home.children', 'children')}',
                    style: TextStyle(color: Colors.grey.shade600)),
              ),
              if (list.isEmpty)
                _EmptyState(text: t.t('home.no_children', 'No children linked yet.'))
              else
                ...list.map((c) => _ChildCard(child: c)),
            ],
          ),
        ),
      ),
    );
  }
}

/// AppBar bell → Alerts inbox, with an unread badge.
class _AlertsBell extends ConsumerWidget {
  const _AlertsBell();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final unread = ref.watch(unreadCountProvider).valueOrNull ?? 0;
    return Stack(
      alignment: Alignment.center,
      children: [
        IconButton(
          tooltip: 'Alerts',
          icon: const Icon(Icons.notifications_outlined, size: 22),
          onPressed: () => context.push('/alerts'),
        ),
        if (unread > 0)
          Positioned(
            top: 8,
            right: 8,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
              constraints: const BoxConstraints(minWidth: 16),
              decoration: BoxDecoration(
                color: const Color(0xFFE11D48),
                borderRadius: BorderRadius.circular(9),
              ),
              alignment: Alignment.center,
              child: Text(unread > 9 ? '9+' : '$unread',
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 10,
                      fontWeight: FontWeight.w700)),
            ),
          ),
      ],
    );
  }
}

class _ChildCard extends ConsumerWidget {
  final Child child;
  const _ChildCard({required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final deviceLabel = child.deviceCount == 1
        ? t.t('child.device', 'device')
        : t.t('child.devices', 'devices');

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () => context.push('/child/${child.id}/map', extra: child),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Container(
                height: 52,
                width: 52,
                decoration: BoxDecoration(
                  gradient: Brand.gradient,
                  borderRadius: BorderRadius.circular(16),
                  image: child.photoUrl != null
                      ? DecorationImage(
                          image: NetworkImage(child.photoUrl!),
                          fit: BoxFit.cover)
                      : null,
                ),
                alignment: Alignment.center,
                child: child.photoUrl == null
                    ? Text(child.initials,
                        style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
                            fontSize: 18))
                    : null,
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(child.name,
                        style: const TextStyle(
                            fontWeight: FontWeight.w700, fontSize: 16)),
                    const SizedBox(height: 3),
                    Text(
                      [
                        if (child.schoolName != null) child.schoolName!,
                        if (child.classGrade != null) child.classGrade!,
                      ].join(' · ').ifEmpty('—'),
                      style:
                          TextStyle(color: Colors.grey.shade600, fontSize: 13),
                    ),
                    const SizedBox(height: 8),
                    Row(children: [
                      _chip(Icons.watch, '${child.deviceCount} $deviceLabel'),
                      const SizedBox(width: 8),
                      _chip(Icons.my_location, t.t('home.track', 'Track live'),
                          accent: true),
                    ]),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: Colors.grey),
            ],
          ),
        ),
      ),
    );
  }

  Widget _chip(IconData icon, String label, {bool accent = false}) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: accent ? const Color(0xFFE7F6FE) : const Color(0xFFEFF2FB),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 13, color: accent ? Brand.cyan : Brand.indigo),
          const SizedBox(width: 4),
          Text(label,
              style: TextStyle(
                  fontSize: 11.5,
                  color: accent ? Brand.cyan : Brand.indigo,
                  fontWeight: FontWeight.w600)),
        ]),
      );
}

class _EmptyState extends StatelessWidget {
  final String text;
  const _EmptyState({required this.text});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 60),
      child: Column(children: [
        Icon(Icons.child_care, size: 48, color: Colors.grey.shade400),
        const SizedBox(height: 12),
        Text(text,
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey.shade600)),
      ]),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final String retryLabel;
  final VoidCallback onRetry;
  const _ErrorState(
      {required this.message, required this.retryLabel, required this.onRetry});
  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 120),
        Icon(Icons.cloud_off, size: 44, color: Colors.grey.shade400),
        const SizedBox(height: 12),
        Center(
            child: Text(message,
                style: const TextStyle(
                    color: Colors.red, fontWeight: FontWeight.w500))),
        const SizedBox(height: 12),
        Center(child: OutlinedButton(onPressed: onRetry, child: Text(retryLabel))),
      ],
    );
  }
}

extension _IfEmpty on String {
  String ifEmpty(String fallback) => trim().isEmpty ? fallback : this;
}
