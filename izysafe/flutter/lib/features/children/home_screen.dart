import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../auth/auth_controller.dart';
import 'child.dart';
import 'children_providers.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final children = ref.watch(childrenProvider);
    final user = ref.watch(authControllerProvider).user;

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
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout, size: 20),
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
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
            onRetry: () => ref.invalidate(childrenProvider),
          ),
          data: (list) => ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 8, 4, 4),
                child: Text('Hi ${user?.displayName ?? ''} 👋',
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w700)),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
                child: Text(
                    list.isEmpty
                        ? 'No children yet'
                        : '${list.length} ${list.length == 1 ? "child" : "children"}',
                    style: TextStyle(color: Colors.grey.shade600)),
              ),
              if (list.isEmpty)
                const _EmptyState()
              else
                ...list.map((c) => _ChildCard(child: c)),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChildCard extends StatelessWidget {
  final Child child;
  const _ChildCard({required this.child});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
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
                    ].join(' · ').ifEmpty('No school set'),
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                  ),
                  const SizedBox(height: 8),
                  Row(children: [
                    _chip(Icons.watch, '${child.deviceCount} device'
                        '${child.deviceCount == 1 ? '' : 's'}'),
                    if (child.role != null) ...[
                      const SizedBox(width: 8),
                      _chip(Icons.person_outline, child.role!),
                    ],
                  ]),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: Colors.grey),
          ],
        ),
      ),
    );
  }

  Widget _chip(IconData icon, String label) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: const Color(0xFFEFF2FB),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 13, color: Brand.indigo),
          const SizedBox(width: 4),
          Text(label,
              style: const TextStyle(
                  fontSize: 11.5,
                  color: Brand.indigo,
                  fontWeight: FontWeight.w600)),
        ]),
      );
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 60),
      child: Column(children: [
        Icon(Icons.child_care, size: 48, color: Colors.grey.shade400),
        const SizedBox(height: 12),
        Text('No children linked to your account yet.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey.shade600)),
      ]),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorState({required this.message, required this.onRetry});
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
        Center(
            child:
                OutlinedButton(onPressed: onRetry, child: const Text('Retry'))),
      ],
    );
  }
}

extension _IfEmpty on String {
  String ifEmpty(String fallback) => trim().isEmpty ? fallback : this;
}
