import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/i18n.dart';
import '../../core/theme.dart';
import 'models.dart';
import 'providers.dart';

/// Subscription / plan management: shows the current plan and the catalog, and
/// starts a gateway checkout for an upgrade. Activation is webhook-driven, so this
/// only opens the checkout URL — the tier updates once the gateway confirms payment.
class PlanScreen extends ConsumerWidget {
  const PlanScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final sub = ref.watch(subscriptionProvider);
    final plans = ref.watch(plansProvider);

    return Scaffold(
      appBar: AppBar(title: Text(t.t('settings.plan', 'Plan'))),
      body: plans.when(
        loading: () => const Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
        error: (_, _) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(plansProvider),
            child: Text(t.t('common.retry', 'Retry')),
          ),
        ),
        data: (list) {
          final currentTier = sub.valueOrNull?.tier ?? 'free';
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            children: [
              _CurrentBanner(info: sub.valueOrNull),
              const SizedBox(height: 16),
              for (final p in list)
                _PlanCardBig(plan: p, isCurrent: p.tier == currentTier),
              const SizedBox(height: 8),
              Text(
                t.t('plan.webhook_note',
                    'Your plan updates automatically once payment is confirmed.'),
                style: TextStyle(fontSize: 12, color: Colors.grey.shade500),
                textAlign: TextAlign.center,
              ),
            ],
          );
        },
      ),
    );
  }
}

class _CurrentBanner extends ConsumerWidget {
  final SubscriptionInfo? info;
  const _CurrentBanner({required this.info});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final tier = info?.tier ?? 'free';
    final tierName = t.t('plan.$tier', _titleCase(tier));
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: Brand.gradient,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          const Icon(Icons.workspace_premium, color: Colors.white, size: 34),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(t.t('plan.current', 'Current plan'),
                    style: const TextStyle(color: Colors.white70, fontSize: 12.5)),
                const SizedBox(height: 2),
                Text(tierName,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.w800)),
                if (info?.periodEnd != null)
                  Text(
                    '${t.t('settings.renews', 'Renews')} ${info!.periodEnd!.toString().split(' ').first}',
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PlanCardBig extends ConsumerStatefulWidget {
  final Plan plan;
  final bool isCurrent;
  const _PlanCardBig({required this.plan, required this.isCurrent});

  @override
  ConsumerState<_PlanCardBig> createState() => _PlanCardBigState();
}

class _PlanCardBigState extends ConsumerState<_PlanCardBig> {
  bool _busy = false;

  Future<void> _upgrade() async {
    final t = ref.read(translatorProvider);
    setState(() => _busy = true);
    try {
      final url = await ref.read(settingsActionsProvider).startCheckout(widget.plan.tier);
      if (url != null && url.isNotEmpty) {
        await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
      } else if (mounted) {
        _snack(t.t('plan.checkout_started', 'Checkout started.'));
      }
    } catch (_) {
      if (mounted) {
        _snack(t.t('plan.payments_unavailable',
            'Online payments aren\'t available yet. Please contact support to upgrade.'));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _snack(String msg) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    final p = widget.plan;
    final name = t.t('plan.${p.tier}', p.name);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: widget.isCurrent
            ? const BorderSide(color: Brand.indigo, width: 1.6)
            : BorderSide(color: Colors.grey.shade200),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(name,
                      style: const TextStyle(
                          fontSize: 17, fontWeight: FontWeight.w800)),
                ),
                if (p.priceLabel.isNotEmpty)
                  Text('${p.priceLabel}/${t.t('plan.month', 'mo')}',
                      style: const TextStyle(
                          fontSize: 15, fontWeight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 10),
            for (final f in p.features)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.check_circle,
                        size: 16, color: Brand.cyan),
                    const SizedBox(width: 8),
                    Expanded(
                        child: Text(f,
                            style: const TextStyle(fontSize: 13.5))),
                  ],
                ),
              ),
            const SizedBox(height: 12),
            if (widget.isCurrent)
              Align(
                alignment: Alignment.centerLeft,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFFEFF2FB),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(t.t('plan.current', 'Current plan'),
                      style: const TextStyle(
                          color: Brand.indigo,
                          fontWeight: FontWeight.w700,
                          fontSize: 12.5)),
                ),
              )
            else if (p.purchasable)
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _busy ? null : _upgrade,
                  child: _busy
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2.2, color: Colors.white))
                      : Text(t.t('plan.choose', 'Choose')),
                ),
              )
            else if (p.tier == 'school')
              Text(t.t('plan.contact_sales', 'Contact sales'),
                  style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

String _titleCase(String s) =>
    s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
