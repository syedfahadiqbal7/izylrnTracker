import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/theme.dart';
import '../enrollments/models.dart';
import '../enrollments/providers.dart';

/// Guided, step-by-step consent setup for a single (usually pending) school
/// enrollment. Walks the parent through the child's day — from the school being
/// able to see the student, to live-location sharing and the ride, and finally
/// how pickup & drop alerts work — then saves all three consents at once.
///
/// Launched from the enrollments list for a pending request; the flat card list
/// stays for later management. Frontend-only: it reuses the existing
/// `GET /enrollments` + `PUT /enrollments/{id}` consent endpoints and adds no
/// new backend (pickup & drop is automatic detection, explained not configured).
class ConsentWizardScreen extends ConsumerStatefulWidget {
  final String enrollmentId;
  const ConsentWizardScreen({super.key, required this.enrollmentId});

  @override
  ConsumerState<ConsentWizardScreen> createState() => _ConsentWizardScreenState();
}

class _ConsentWizardScreenState extends ConsumerState<ConsentWizardScreen> {
  final _controller = PageController();
  int _step = 0;
  bool _seeded = false;

  // Accumulated consent choices (seeded from the enrollment, saved on finish).
  bool _approve = false;
  bool _shareLocation = false;
  bool _busTracking = false;

  bool _submitting = false;

  static const _lastStep = 5; // 0..5 (Welcome, Approve, Location, Bus, Pickup, Review)

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _seed(ParentEnrollment e) {
    if (_seeded) return;
    _seeded = true;
    _approve = e.parentOptIn;
    _shareLocation = e.locationOptIn;
    _busTracking = e.busOptIn;
  }

  void _goTo(int step) {
    setState(() => _step = step);
    _controller.animateToPage(
      step,
      duration: const Duration(milliseconds: 260),
      curve: Curves.easeInOut,
    );
  }

  void _next() {
    if (_step < _lastStep) _goTo(_step + 1);
  }

  void _back() {
    if (_step > 0) _goTo(_step - 1);
  }

  Future<void> _finish(ParentEnrollment e) async {
    setState(() => _submitting = true);
    final t = ref.read(translatorProvider);
    try {
      await ref.read(updateConsentProvider)(
        e.id,
        parentOptIn: _approve,
        locationOptIn: _approve && _shareLocation,
        busOptIn: _approve && _busTracking,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(t.t('consent.saved', 'Setup saved.')),
      ));
      context.pop();
    } catch (_) {
      if (!mounted) return;
      setState(() => _submitting = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(t.t('consent.save_error', 'Could not save. Please try again.')),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    final enrollments = ref.watch(enrollmentsProvider);

    return Scaffold(
      body: enrollments.when(
        loading: () => const Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
        error: (_, _) => _NotFound(
          message: t.t('consent.load_error', 'Could not load this request.'),
          onBack: () => context.pop(),
        ),
        data: (list) {
          final match = list.where((e) => e.id == widget.enrollmentId);
          if (match.isEmpty) {
            return _NotFound(
              message: t.t('consent.not_found', 'This request is no longer available.'),
              onBack: () => context.pop(),
            );
          }
          final e = match.first;
          _seed(e);
          return SafeArea(
            child: Column(
              children: [
                _WizardHeader(step: _step, total: _lastStep + 1, onClose: () => context.pop()),
                Expanded(
                  child: PageView(
                    controller: _controller,
                    physics: const NeverScrollableScrollPhysics(),
                    onPageChanged: (i) => setState(() => _step = i),
                    children: [
                      _WelcomeStep(enrollment: e),
                      _ApproveStep(
                        enrollment: e,
                        value: _approve,
                        onChanged: (v) => setState(() => _approve = v),
                      ),
                      _ToggleStep(
                        icon: Icons.my_location_rounded,
                        title: t.t('consent.loc_title', 'Share live location'),
                        lead: t.t('consent.loc_lead',
                            'Let the school see where your child is during the school day and the ride home.'),
                        bullets: [
                          t.t('consent.loc_b1', 'Only while an active school day is in progress.'),
                          t.t('consent.loc_b2', 'You can turn this off any time from School requests.'),
                        ],
                        switchLabel: t.t('consent.loc_switch', 'Share live location'),
                        value: _shareLocation,
                        enabled: _approve,
                        disabledHint: t.t('consent.needs_approve',
                            'Approve the school first to enable this.'),
                        onChanged: (v) => setState(() => _shareLocation = v),
                      ),
                      _ToggleStep(
                        icon: Icons.directions_bus_rounded,
                        title: t.t('consent.bus_title', 'Bus & ride tracking'),
                        lead: t.t('consent.bus_lead',
                            'Get the bus assignment and track the ride to and from school.'),
                        bullets: [
                          t.t('consent.bus_b1', 'See the bus on the map and its estimated arrival.'),
                          t.t('consent.bus_b2', 'Optional — skip it if your child does not take the bus.'),
                        ],
                        switchLabel: t.t('consent.bus_switch', 'Bus tracking'),
                        value: _busTracking,
                        enabled: _approve,
                        disabledHint: t.t('consent.needs_approve',
                            'Approve the school first to enable this.'),
                        onChanged: (v) => setState(() => _busTracking = v),
                      ),
                      _PickupStep(enrollment: e),
                      _ReviewStep(
                        enrollment: e,
                        approve: _approve,
                        shareLocation: _shareLocation,
                        busTracking: _busTracking,
                      ),
                    ],
                  ),
                ),
                _WizardFooter(
                  step: _step,
                  lastStep: _lastStep,
                  canAdvance: _step != 1 || _approve,
                  blockedHint: t.t('consent.needs_approve_next',
                      'Turn on approval to continue, or decline below.'),
                  submitting: _submitting,
                  onBack: _back,
                  onNext: _next,
                  onFinish: () => _finish(e),
                  onDecline: _step == 1 && !_approve ? () => context.pop() : null,
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// Gradient top bar with a progress track and a close button.
class _WizardHeader extends ConsumerWidget {
  final int step;
  final int total;
  final VoidCallback onClose;
  const _WizardHeader({required this.step, required this.total, required this.onClose});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      decoration: const BoxDecoration(
        gradient: Brand.gradient,
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(28),
          bottomRight: Radius.circular(28),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  t.t('consent.title', 'Set up school access'),
                  style: const TextStyle(
                      color: Colors.white, fontSize: 18, fontWeight: FontWeight.w800),
                ),
              ),
              IconButton(
                onPressed: onClose,
                icon: const Icon(Icons.close_rounded, color: Colors.white),
                tooltip: t.t('common.close', 'Close'),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              for (int i = 0; i < total; i++) ...[
                Expanded(
                  child: Container(
                    height: 5,
                    decoration: BoxDecoration(
                      color: i <= step
                          ? Colors.white
                          : Colors.white.withValues(alpha: 0.32),
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                ),
                if (i != total - 1) const SizedBox(width: 5),
              ],
            ],
          ),
          const SizedBox(height: 8),
          Text(
            t.t('consent.step_of', 'Step {n} of {total}')
                .replaceFirst('{n}', '${step + 1}')
                .replaceFirst('{total}', '$total'),
            style: TextStyle(
                color: Colors.white.withValues(alpha: 0.9),
                fontSize: 13,
                fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

/// Shared scrollable body shell for a step: big icon, title, lead text, child.
class _StepBody extends StatelessWidget {
  final IconData icon;
  final Color iconBg;
  final Color iconFg;
  final String title;
  final String lead;
  final List<Widget> children;
  const _StepBody({
    required this.icon,
    required this.iconBg,
    required this.iconFg,
    required this.title,
    required this.lead,
    this.children = const [],
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(color: iconBg, borderRadius: BorderRadius.circular(16)),
            child: Icon(icon, color: iconFg, size: 28),
          ),
          const SizedBox(height: 18),
          Text(title,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
          const SizedBox(height: 10),
          Text(lead, style: TextStyle(color: Colors.grey.shade700, fontSize: 15, height: 1.4)),
          const SizedBox(height: 18),
          ...children,
        ],
      ),
    );
  }
}

class _Bullet extends StatelessWidget {
  final String text;
  const _Bullet(this.text);
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(Icons.check_circle_rounded, size: 18, color: Brand.cyan),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text,
                style: TextStyle(color: Colors.grey.shade800, fontSize: 14, height: 1.35)),
          ),
        ],
      ),
    );
  }
}

class _WelcomeStep extends ConsumerWidget {
  final ParentEnrollment enrollment;
  const _WelcomeStep({required this.enrollment});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final who = [
      enrollment.childName,
      if (enrollment.classGrade != null) enrollment.classGrade!,
    ].join(' · ');
    return _StepBody(
      icon: Icons.handshake_rounded,
      iconBg: const Color(0xFFEFF2FB),
      iconFg: Brand.indigo,
      title: t.t('consent.welcome_title', 'Welcome to {school}').replaceFirst(
          '{school}', enrollment.schoolName),
      lead: t.t('consent.welcome_lead',
          'Your school added your child. In a few quick steps you decide exactly what to share — from the school seeing your student, to the ride home, to pickup & drop alerts.'),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                      gradient: Brand.gradient, borderRadius: BorderRadius.circular(12)),
                  child: const Icon(Icons.school_rounded, color: Colors.white, size: 22),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(enrollment.schoolName,
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                      const SizedBox(height: 2),
                      Text(who,
                          style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        _Bullet(t.t('consent.welcome_b1', 'You are always in control — change or withdraw any time.')),
        _Bullet(t.t('consent.welcome_b2', 'Nothing is shared until you approve it here.')),
      ],
    );
  }
}

class _ApproveStep extends ConsumerWidget {
  final ParentEnrollment enrollment;
  final bool value;
  final ValueChanged<bool> onChanged;
  const _ApproveStep({
    required this.enrollment,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return _StepBody(
      icon: Icons.verified_user_rounded,
      iconBg: const Color(0xFFEFF2FB),
      iconFg: Brand.indigo,
      title: t.t('consent.approve_title', 'Approve the school'),
      lead: t.t('consent.approve_lead',
          'Turn this on so the school can see your student in their dashboard and roster. This is the master switch — the next steps only apply once it is on.'),
      children: [
        Card(
          child: SwitchListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            title: Text(
              t.t('consent.approve_switch', 'Let {school} see this student')
                  .replaceFirst('{school}', enrollment.schoolName),
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            value: value,
            onChanged: onChanged,
          ),
        ),
        const SizedBox(height: 16),
        _Bullet(t.t('consent.approve_b1',
            'The school sees your student’s name, class and attendance only.')),
        _Bullet(t.t('consent.approve_b2',
            'Location and bus tracking stay off until you choose them next.')),
      ],
    );
  }
}

/// A step that frames one optional consent and a single switch for it.
class _ToggleStep extends StatelessWidget {
  final IconData icon;
  final String title;
  final String lead;
  final List<String> bullets;
  final String switchLabel;
  final bool value;
  final bool enabled;
  final String disabledHint;
  final ValueChanged<bool> onChanged;
  const _ToggleStep({
    required this.icon,
    required this.title,
    required this.lead,
    required this.bullets,
    required this.switchLabel,
    required this.value,
    required this.enabled,
    required this.disabledHint,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return _StepBody(
      icon: icon,
      iconBg: const Color(0xFFE7F6FE),
      iconFg: Brand.cyan,
      title: title,
      lead: lead,
      children: [
        for (final b in bullets) _Bullet(b),
        const SizedBox(height: 6),
        Card(
          child: SwitchListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            title: Text(switchLabel, style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: enabled ? null : Text(disabledHint, style: const TextStyle(fontSize: 12)),
            value: enabled && value,
            onChanged: enabled ? onChanged : null,
          ),
        ),
      ],
    );
  }
}

/// Pickup & drop — the end of the journey. Frontend-only: automatic detection is
/// explained here, not configured (backend F17 records it from the school zone).
class _PickupStep extends ConsumerWidget {
  final ParentEnrollment enrollment;
  const _PickupStep({required this.enrollment});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return _StepBody(
      icon: Icons.directions_walk_rounded,
      iconBg: const Color(0xFFDCFCE7),
      iconFg: const Color(0xFF15803D),
      title: t.t('consent.pickup_title', 'Pickup & drop'),
      lead: t.t('consent.pickup_lead',
          'This is automatic. When your child reaches school in the morning and leaves at the end of the day, you get a pickup & drop alert — no setup needed.'),
      children: [
        _Bullet(t.t('consent.pickup_b1',
            'Alerts arrive around arrival and dismissal time at the school.')),
        _Bullet(t.t('consent.pickup_b2',
            'They tell you whether your child left on foot or in a vehicle.')),
        _Bullet(t.t('consent.pickup_b3',
            'Find every pickup & drop in your Alerts inbox.')),
        const SizedBox(height: 6),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFFF1FBF4),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFBEEBCC)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.notifications_active_rounded,
                  size: 20, color: Color(0xFF15803D)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  t.t('consent.pickup_note',
                      'Pickup & drop alerts need live location on — turn it on in the previous step to get them.'),
                  style: const TextStyle(fontSize: 13, height: 1.35, color: Color(0xFF166534)),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ReviewStep extends ConsumerWidget {
  final ParentEnrollment enrollment;
  final bool approve;
  final bool shareLocation;
  final bool busTracking;
  const _ReviewStep({
    required this.enrollment,
    required this.approve,
    required this.shareLocation,
    required this.busTracking,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return _StepBody(
      icon: Icons.fact_check_rounded,
      iconBg: const Color(0xFFEFF2FB),
      iconFg: Brand.indigo,
      title: t.t('consent.review_title', 'Review & finish'),
      lead: t.t('consent.review_lead',
          'Here is what you are sharing with the school. Tap Finish to save — you can change any of it later.'),
      children: [
        Card(
          child: Column(
            children: [
              _ReviewRow(
                label: t.t('consent.review_approve', 'School can see student'),
                on: approve,
              ),
              const Divider(height: 1),
              _ReviewRow(
                label: t.t('consent.loc_switch', 'Share live location'),
                on: approve && shareLocation,
              ),
              const Divider(height: 1),
              _ReviewRow(
                label: t.t('consent.bus_switch', 'Bus tracking'),
                on: approve && busTracking,
              ),
              const Divider(height: 1),
              _ReviewRow(
                label: t.t('consent.pickup_title', 'Pickup & drop'),
                on: approve && shareLocation,
                onText: t.t('consent.automatic', 'Automatic'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ReviewRow extends ConsumerWidget {
  final String label;
  final bool on;
  final String? onText;
  const _ReviewRow({required this.label, required this.on, this.onText});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final bg = on ? const Color(0xFFDCFCE7) : const Color(0xFFF1F3F8);
    final fg = on ? const Color(0xFF15803D) : Colors.grey.shade600;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Expanded(child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600))),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
            child: Text(
              on ? (onText ?? t.t('consent.on', 'On')) : t.t('consent.off', 'Off'),
              style: TextStyle(color: fg, fontWeight: FontWeight.w700, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }
}

class _WizardFooter extends ConsumerWidget {
  final int step;
  final int lastStep;
  final bool canAdvance;
  final String blockedHint;
  final bool submitting;
  final VoidCallback onBack;
  final VoidCallback onNext;
  final VoidCallback onFinish;
  final VoidCallback? onDecline;
  const _WizardFooter({
    required this.step,
    required this.lastStep,
    required this.canAdvance,
    required this.blockedHint,
    required this.submitting,
    required this.onBack,
    required this.onNext,
    required this.onFinish,
    required this.onDecline,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final isLast = step == lastStep;
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 20),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: Colors.grey.shade200)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (step == 1 && !canAdvance)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Text(blockedHint,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
            ),
          Row(
            children: [
              if (step > 0)
                Expanded(
                  child: OutlinedButton(
                    onPressed: submitting ? null : onBack,
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size.fromHeight(52),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                    child: Text(t.t('common.back', 'Back')),
                  ),
                ),
              if (step > 0) const SizedBox(width: 12),
              Expanded(
                flex: 2,
                child: FilledButton(
                  onPressed: submitting || !canAdvance ? null : (isLast ? onFinish : onNext),
                  child: submitting
                      ? const SizedBox(
                          height: 22,
                          width: 22,
                          child: CircularProgressIndicator(
                              strokeWidth: 2.4, color: Colors.white),
                        )
                      : Text(isLast
                          ? t.t('consent.finish', 'Finish')
                          : t.t('common.next', 'Next')),
                ),
              ),
            ],
          ),
          if (onDecline != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: TextButton(
                onPressed: submitting ? null : onDecline,
                child: Text(t.t('consent.decline', 'Decline for now')),
              ),
            ),
        ],
      ),
    );
  }
}

class _NotFound extends ConsumerWidget {
  final String message;
  final VoidCallback onBack;
  const _NotFound({required this.message, required this.onBack});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return SafeArea(
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline_rounded, size: 48, color: Colors.grey.shade400),
              const SizedBox(height: 12),
              Text(message, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              FilledButton(onPressed: onBack, child: Text(t.t('common.back', 'Back'))),
            ],
          ),
        ),
      ),
    );
  }
}
