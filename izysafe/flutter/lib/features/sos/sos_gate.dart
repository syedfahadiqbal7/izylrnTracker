import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/i18n.dart';
import '../../router.dart';
import '../auth/auth_controller.dart';
import '../tracking/models.dart';

/// App-wide active-SOS poll, independent of the Live Map screen. Runs only while
/// authenticated. This is the real-time channel for the global SOS popup in dev,
/// where FCM/Firebase push are not configured — it polls `/sos/active` every few
/// seconds so an SOS surfaces on ANY screen, not just the child's map.
final globalActiveSosProvider = StreamProvider<List<SosEvent>>((ref) async* {
  final auth = ref.watch(authControllerProvider);
  if (auth.status != AuthStatus.authenticated) {
    yield const <SosEvent>[];
    return;
  }
  final api = ref.watch(apiClientProvider);
  var emitted = false;
  while (true) {
    try {
      final data = await api.get('/sos/active') as List<dynamic>;
      yield data
          .map((e) => SosEvent.fromJson(e as Map<String, dynamic>))
          .toList(growable: false);
      emitted = true;
    } catch (_) {
      if (!emitted) {
        yield const <SosEvent>[];
        emitted = true;
      }
    }
    await Future.delayed(const Duration(seconds: 6));
  }
});

const _sosRed = Color(0xFFE11D48);

/// Wraps the whole app (mounted in MaterialApp.router's `builder`) and paints a
/// full-screen, non-dismissible SOS overlay on top of every screen whenever a
/// child has an active SOS. The overlay is declarative: it appears the moment an
/// SOS is active and disappears automatically once it's resolved (by anyone).
class SosGate extends ConsumerWidget {
  final Widget child;
  const SosGate({super.key, required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final active = ref.watch(globalActiveSosProvider).valueOrNull ?? const <SosEvent>[];
    final sos = active.isEmpty ? null : active.first;
    return Stack(
      textDirection: TextDirection.ltr,
      children: [
        child,
        if (sos != null) Positioned.fill(child: _SosOverlay(sos: sos)),
      ],
    );
  }
}

class _SosOverlay extends ConsumerStatefulWidget {
  final SosEvent sos;
  const _SosOverlay({required this.sos});

  @override
  ConsumerState<_SosOverlay> createState() => _SosOverlayState();
}

class _SosOverlayState extends ConsumerState<_SosOverlay> {
  bool _resolving = false;

  Future<void> _resolve() async {
    setState(() => _resolving = true);
    try {
      await ref.read(apiClientProvider).put('/sos/${widget.sos.id}/resolve');
      ref.invalidate(globalActiveSosProvider);
    } catch (_) {
      if (mounted) setState(() => _resolving = false);
    }
  }

  void _openMap() {
    ref.read(routerProvider).go('/child/${widget.sos.childId}/map');
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    final sos = widget.sos;
    final name = sos.childName ?? t.t('sos.a_child', 'your child');
    final time = TimeOfDay.fromDateTime(sos.triggeredAt).format(context);

    // Block the hardware back button — an SOS must be acknowledged, not dismissed.
    return PopScope(
      canPop: false,
      child: Material(
        color: _sosRed,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(28),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Icon(Icons.crisis_alert, color: Colors.white, size: 88),
                const SizedBox(height: 20),
                Text(
                  t.t('sos.title', 'SOS Emergency'),
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 30,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '${t.t('sos.triggered_by', 'Emergency alert from')} $name',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white, fontSize: 18),
                ),
                const SizedBox(height: 6),
                Text(
                  '${t.t('sos.at', 'at')} $time'
                  '${sos.approximate ? ' · ${t.t('sos.approx_location', 'approximate location')}' : ''}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white70, fontSize: 14),
                ),
                const SizedBox(height: 36),
                FilledButton.icon(
                  onPressed: _openMap,
                  style: FilledButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: _sosRed,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  icon: const Icon(Icons.map),
                  label: Text(t.t('sos.view_on_map', 'View on live map')),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _resolving ? null : _resolve,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: const BorderSide(color: Colors.white70),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  icon: _resolving
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.check_circle_outline),
                  label: Text(
                    _resolving
                        ? t.t('sos.resolving', 'Resolving…')
                        : t.t('sos.resolve', 'Mark as resolved'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
