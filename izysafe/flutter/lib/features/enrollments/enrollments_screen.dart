import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/i18n.dart';
import 'models.dart';
import 'providers.dart';

/// Parent-side consent: the schools that have added each child, and switches to
/// grant/withdraw visibility, live-location, and bus tracking (Model 1 consent loop).
class EnrollmentsScreen extends ConsumerWidget {
  const EnrollmentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final enrollments = ref.watch(enrollmentsProvider);
    return Scaffold(
      appBar: AppBar(title: Text(t.t('enroll.title', 'School requests'))),
      body: enrollments.when(
        loading: () => const Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
        error: (_, _) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(enrollmentsProvider),
            child: Text(t.t('common.retry', 'Retry')),
          ),
        ),
        data: (list) {
          if (list.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.school_outlined, size: 48, color: Colors.grey.shade400),
                  const SizedBox(height: 12),
                  Text(t.t('enroll.empty', 'No school requests yet.'),
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey.shade600)),
                ]),
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            children: [
              Text(
                t.t('enroll.desc',
                    'Schools that have added your child. Approve to let a school see them, and choose what to share.'),
                style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
              ),
              const SizedBox(height: 12),
              for (final e in list) _EnrollmentCard(enrollment: e),
            ],
          );
        },
      ),
    );
  }
}

class _EnrollmentCard extends ConsumerStatefulWidget {
  final ParentEnrollment enrollment;
  const _EnrollmentCard({required this.enrollment});

  @override
  ConsumerState<_EnrollmentCard> createState() => _EnrollmentCardState();
}

class _EnrollmentCardState extends ConsumerState<_EnrollmentCard> {
  bool _busy = false;

  Future<void> _set({bool? parentOptIn, bool? busOptIn, bool? locationOptIn}) async {
    setState(() => _busy = true);
    try {
      await ref.read(updateConsentProvider)(
        widget.enrollment.id,
        parentOptIn: parentOptIn,
        busOptIn: busOptIn,
        locationOptIn: locationOptIn,
      );
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(ref
                .read(translatorProvider)
                .t('enroll.save_error', 'Could not update. Please try again.'))));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    final e = widget.enrollment;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 8, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(e.schoolName,
                            style: const TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 16)),
                        const SizedBox(height: 2),
                        Text(
                          [e.childName, if (e.classGrade != null) e.classGrade!]
                              .join(' · '),
                          style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                  _StatusChip(approved: e.parentOptIn),
                ],
              ),
            ),
            const SizedBox(height: 4),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(t.t('enroll.visibility', 'Let the school see this student')),
              subtitle: e.parentOptIn
                  ? null
                  : Text(t.t('enroll.visibility_hint', 'Turn on to approve the enrollment.'),
                      style: const TextStyle(fontSize: 12)),
              value: e.parentOptIn,
              onChanged: _busy ? null : (v) => _set(parentOptIn: v),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(t.t('enroll.share_location', 'Share live location')),
              value: e.locationOptIn,
              onChanged: (_busy || !e.parentOptIn) ? null : (v) => _set(locationOptIn: v),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(t.t('enroll.bus_tracking', 'Bus tracking')),
              value: e.busOptIn,
              onChanged: (_busy || !e.parentOptIn) ? null : (v) => _set(busOptIn: v),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends ConsumerWidget {
  final bool approved;
  const _StatusChip({required this.approved});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final bg = approved ? const Color(0xFFDCFCE7) : const Color(0xFFFEF3C7);
    final fg = approved ? const Color(0xFF15803D) : const Color(0xFF92600A);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
      child: Text(
        approved ? t.t('enroll.consented', 'Approved') : t.t('enroll.pending', 'Pending'),
        style: TextStyle(color: fg, fontWeight: FontWeight.w700, fontSize: 12),
      ),
    );
  }
}
