import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/i18n.dart';
import '../../core/theme.dart';
import '../auth/auth_controller.dart';
import '../children/children_providers.dart';
import 'models.dart';
import 'providers.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final profile = ref.watch(profileProvider);

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Text(t.t('nav.settings', 'Settings'),
            style: const TextStyle(fontWeight: FontWeight.w700)),
      ),
      body: profile.when(
        loading: () =>
            const Center(child: CircularProgressIndicator(strokeWidth: 2.6)),
        error: (_, _) =>Center(
          child: TextButton(
            onPressed: () => ref.invalidate(profileProvider),
            child: Text(t.t('common.retry', 'Retry')),
          ),
        ),
        data: (p) => ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
          children: [
            _ProfileCard(profile: p),
            const SizedBox(height: 16),
            _SectionLabel(t.t('settings.family', 'Family & children')),
            const _FamilyCard(),
            const SizedBox(height: 16),
            _SectionLabel(t.t('settings.notifications', 'Notifications')),
            _NotificationsCard(profile: p),
            const SizedBox(height: 16),
            _SectionLabel(t.t('app.language', 'Language')),
            _LanguageCard(profile: p),
            const SizedBox(height: 16),
            _SectionLabel(t.t('settings.emergency_contacts', 'Emergency contacts')),
            const _EmergencyCard(),
            const SizedBox(height: 16),
            _SectionLabel(t.t('settings.plan', 'Plan')),
            const _PlanCard(),
            const SizedBox(height: 24),
            const _LogoutButton(),
            const SizedBox(height: 16),
            Center(
              child: Text('izyLrn • v1.0.0',
                  style: TextStyle(color: Colors.grey.shade400, fontSize: 12)),
            ),
          ],
        ),
      ),
    );
  }
}

// --------------------------------------------------------------------------- //
class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
        child: Text(text.toUpperCase(),
            style: TextStyle(
                color: Colors.grey.shade500,
                fontSize: 11.5,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.5)),
      );
}

class _Panel extends StatelessWidget {
  final Widget child;
  const _Panel({required this.child});
  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: const Color(0xFFEBEEF6)),
        ),
        child: child,
      );
}

// --------------------------------------------------------------------------- profile
class _ProfileCard extends ConsumerWidget {
  final ProfileSettings profile;
  const _ProfileCard({required this.profile});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return _Panel(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              height: 56,
              width: 56,
              decoration: BoxDecoration(
                gradient: Brand.gradient,
                borderRadius: BorderRadius.circular(18),
                image: profile.photoUrl != null
                    ? DecorationImage(
                        image: NetworkImage(profile.photoUrl!), fit: BoxFit.cover)
                    : null,
              ),
              alignment: Alignment.center,
              child: profile.photoUrl == null
                  ? Text(profile.initials,
                      style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                          fontSize: 20))
                  : null,
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(profile.displayName,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 17)),
                  const SizedBox(height: 2),
                  Text(profile.phone,
                      style: TextStyle(color: Colors.grey.shade600, fontSize: 13.5)),
                  if (profile.email != null && profile.email!.isNotEmpty)
                    Text(profile.email!,
                        style: TextStyle(
                            color: Colors.grey.shade600, fontSize: 13)),
                ],
              ),
            ),
            OutlinedButton(
              onPressed: () => _editProfile(context, ref, profile),
              child: Text(t.t('common.edit', 'Edit')),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _editProfile(
      BuildContext context, WidgetRef ref, ProfileSettings p) async {
    final t = ref.read(translatorProvider);
    final nameCtl = TextEditingController(text: p.name ?? '');
    final emailCtl = TextEditingController(text: p.email ?? '');
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t.t('settings.edit_profile', 'Edit profile')),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: nameCtl,
                decoration: InputDecoration(
                    labelText: t.t('settings.name', 'Name'))),
            const SizedBox(height: 12),
            TextField(
                controller: emailCtl,
                keyboardType: TextInputType.emailAddress,
                decoration: InputDecoration(
                    labelText: t.t('settings.email', 'Email'))),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: Text(t.t('common.cancel', 'Cancel'))),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(t.t('common.save', 'Save'))),
        ],
      ),
    );
    if (saved == true) {
      await ref.read(settingsActionsProvider).updateProfile(
            name: nameCtl.text.trim().isEmpty ? null : nameCtl.text.trim(),
            email: emailCtl.text.trim().isEmpty ? null : emailCtl.text.trim(),
          );
    }
  }
}

// --------------------------------------------------------------------------- family
class _FamilyCard extends ConsumerWidget {
  const _FamilyCard();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final children = ref.watch(childrenProvider);
    return _Panel(
      child: children.when(
        loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2.2))),
        error: (_, _) =>Padding(
            padding: const EdgeInsets.all(16),
            child: Text(t.t('alerts.load_error', 'Could not load.'),
                style: const TextStyle(color: Colors.red))),
        data: (list) => list.isEmpty
            ? Padding(
                padding: const EdgeInsets.all(16),
                child: Text(t.t('home.no_children', 'No children yet'),
                    style: TextStyle(color: Colors.grey.shade600)))
            : Column(
                children: [
                  for (var i = 0; i < list.length; i++) ...[
                    if (i > 0) const Divider(height: 1),
                    ListTile(
                      leading: CircleAvatar(
                        backgroundColor: const Color(0xFFEFF2FB),
                        child: Text(list[i].initials,
                            style: const TextStyle(
                                color: Brand.indigo,
                                fontWeight: FontWeight.w700,
                                fontSize: 14)),
                      ),
                      title: Text(list[i].name,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      subtitle: Text([
                        if (list[i].schoolName != null) list[i].schoolName!,
                        if (list[i].role != null) list[i].role!,
                      ].join(' · ')),
                      trailing: const Icon(Icons.chevron_right,
                          color: Colors.grey, size: 20),
                      onTap: () => context.push('/child/${list[i].id}/map',
                          extra: list[i]),
                    ),
                  ],
                ],
              ),
      ),
    );
  }
}

// --------------------------------------------------------------------------- notifications
class _NotificationsCard extends ConsumerWidget {
  final ProfileSettings profile;
  const _NotificationsCard({required this.profile});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return _Panel(
      child: Column(
        children: [
          SwitchListTile(
            value: profile.quietHoursOn,
            title: Text(t.t('settings.quiet_hours', 'Quiet hours'),
                style: const TextStyle(fontWeight: FontWeight.w600)),
            subtitle: Text(profile.quietHoursOn
                ? '${profile.quietFrom} – ${profile.quietTo}'
                : t.t('settings.quiet_hours_desc',
                    'Mute non-urgent alerts during set hours.')),
            onChanged: (on) async {
              if (on) {
                await _pickQuietHours(context, ref);
              } else {
                await ref.read(settingsActionsProvider).setQuietHours(null, null);
              }
            },
          ),
          if (profile.quietHoursOn)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: TextButton(
                  onPressed: () => _pickQuietHours(context, ref),
                  child: Text(t.t('settings.change_hours', 'Change hours')),
                ),
              ),
            ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                const Icon(Icons.verified_user,
                    size: 16, color: Color(0xFFE11D48)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    t.t('settings.sos_always',
                        'SOS emergency alerts always come through.'),
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 12.5),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _pickQuietHours(BuildContext context, WidgetRef ref) async {
    final from = await showTimePicker(
        context: context,
        initialTime: const TimeOfDay(hour: 22, minute: 0),
        helpText: ref.read(translatorProvider).t('settings.quiet_from', 'Mute from'));
    if (from == null || !context.mounted) return;
    final to = await showTimePicker(
        context: context,
        initialTime: const TimeOfDay(hour: 7, minute: 0),
        helpText: ref.read(translatorProvider).t('settings.quiet_to', 'Mute until'));
    if (to == null) return;
    String hhmm(TimeOfDay t) =>
        '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
    await ref.read(settingsActionsProvider).setQuietHours(hhmm(from), hhmm(to));
  }
}

// --------------------------------------------------------------------------- language
class _LanguageCard extends ConsumerWidget {
  final ProfileSettings profile;
  const _LanguageCard({required this.profile});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final current = ref.watch(localeControllerProvider);
    final active = supportedLocales.firstWhere((l) => l.code == current,
        orElse: () => supportedLocales.first);
    return _Panel(
      child: ListTile(
        leading: const Icon(Icons.language, color: Brand.indigo),
        title: Text(active.nativeName,
            style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(active.name),
        trailing: const Icon(Icons.expand_more, color: Colors.grey),
        onTap: () => _pick(context, ref, current),
      ),
    );
  }

  Future<void> _pick(
      BuildContext context, WidgetRef ref, String current) async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final l in supportedLocales)
              ListTile(
                title: Text(l.nativeName,
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text(l.name),
                trailing: l.code == current
                    ? const Icon(Icons.check, color: Brand.cyan)
                    : null,
                onTap: () async {
                  Navigator.pop(ctx);
                  // Local switch (persist + RTL) + sync to the backend profile.
                  await ref.read(localeControllerProvider.notifier).set(l.code);
                  await ref.read(settingsActionsProvider).setLanguage(l.code);
                },
              ),
          ],
        ),
      ),
    );
  }
}

// --------------------------------------------------------------------------- emergency
class _EmergencyCard extends ConsumerWidget {
  const _EmergencyCard();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final profile = ref.watch(profileProvider).valueOrNull;
    final isPremium = profile?.tier == 'premium';
    final contacts = ref.watch(emergencyContactsProvider);

    if (!isPremium) {
      return _Panel(
        child: ListTile(
          leading: const Icon(Icons.workspace_premium, color: Color(0xFFF59E0B)),
          title: Text(t.t('settings.emergency_premium',
              'Emergency contacts are a Premium feature.')),
          subtitle: Text(t.t('settings.emergency_premium_hint',
              'Upgrade to add trusted contacts who are alerted on an SOS.')),
        ),
      );
    }

    return _Panel(
      child: contacts.when(
        loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2.2))),
        error: (_, _) =>Padding(
            padding: const EdgeInsets.all(16),
            child: Text(t.t('alerts.load_error', 'Could not load.'),
                style: const TextStyle(color: Colors.red))),
        data: (list) => list.isEmpty
            ? Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                    t.t('settings.no_emergency', 'No emergency contacts yet.'),
                    style: TextStyle(color: Colors.grey.shade600)))
            : Column(
                children: [
                  for (var i = 0; i < list.length; i++) ...[
                    if (i > 0) const Divider(height: 1),
                    ListTile(
                      leading: const CircleAvatar(
                        backgroundColor: Color(0xFFFDE7EC),
                        child: Icon(Icons.contact_phone,
                            color: Color(0xFFE11D48), size: 20),
                      ),
                      title: Text(list[i].name,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      subtitle: Text([
                        list[i].phone,
                        if (list[i].relationship != null) list[i].relationship!,
                        list[i].childName,
                      ].join(' · ')),
                      trailing: IconButton(
                        icon: const Icon(Icons.call, color: Brand.indigo),
                        onPressed: () async {
                          final uri = Uri(scheme: 'tel', path: list[i].phone);
                          if (await canLaunchUrl(uri)) await launchUrl(uri);
                        },
                      ),
                    ),
                  ],
                ],
              ),
      ),
    );
  }
}

// --------------------------------------------------------------------------- plan
class _PlanCard extends ConsumerWidget {
  const _PlanCard();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final sub = ref.watch(subscriptionProvider);
    return _Panel(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: sub.when(
          loading: () => const Center(
              child: Padding(
                  padding: EdgeInsets.all(8),
                  child: CircularProgressIndicator(strokeWidth: 2.2))),
          error: (_, _) =>Text(t.t('alerts.load_error', 'Could not load.'),
              style: const TextStyle(color: Colors.red)),
          data: (s) {
            final tierName = t.t('plan.${s.tier}', _titleCase(s.tier));
            return Row(
              children: [
                Container(
                  height: 46,
                  width: 46,
                  decoration: BoxDecoration(
                    gradient: Brand.gradient,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: const Icon(Icons.workspace_premium, color: Colors.white),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${t.t('settings.plan', 'Plan')}: $tierName',
                          style: const TextStyle(
                              fontWeight: FontWeight.w700, fontSize: 15)),
                      const SizedBox(height: 2),
                      Text(
                        s.periodEnd != null
                            ? '${t.t('settings.renews', 'Renews')} ${s.periodEnd!.toLocal().toString().split(' ').first}'
                            : t.t('plan.status_${s.status}', _titleCase(s.status)),
                        style: TextStyle(
                            color: Colors.grey.shade600, fontSize: 12.5),
                      ),
                    ],
                  ),
                ),
                TextButton(
                  onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                        content: Text(
                            t.t('settings.coming_soon', 'Plan management is coming soon.'))),
                  ),
                  child: Text(t.t('settings.manage_plan', 'Manage')),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

// --------------------------------------------------------------------------- logout
class _LogoutButton extends ConsumerWidget {
  const _LogoutButton();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return OutlinedButton.icon(
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFFE11D48),
        side: const BorderSide(color: Color(0xFFF3C6CF)),
        minimumSize: const Size.fromHeight(50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
      icon: const Icon(Icons.logout, size: 18),
      label: Text(t.t('app.sign_out', 'Sign out')),
      onPressed: () async {
        final ok = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: Text(t.t('app.sign_out', 'Sign out')),
            content: Text(
                t.t('settings.logout_confirm', 'Sign out of izyLrn on this device?')),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(ctx, false),
                  child: Text(t.t('common.cancel', 'Cancel'))),
              FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFFE11D48)),
                  onPressed: () => Navigator.pop(ctx, true),
                  child: Text(t.t('app.sign_out', 'Sign out'))),
            ],
          ),
        );
        if (ok == true) {
          await ref.read(authControllerProvider.notifier).logout();
        }
      },
    );
  }
}

String _titleCase(String s) =>
    s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
