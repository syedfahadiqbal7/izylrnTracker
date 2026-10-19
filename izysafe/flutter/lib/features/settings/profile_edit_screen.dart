import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import '../../core/i18n.dart';
import 'models.dart';
import 'providers.dart';

const _fallbackCenter = LatLng(25.2048, 55.2708); // Dubai

/// Loads the current profile, then renders the edit form. Works whether reached
/// from Settings or opened directly (e.g. a web refresh on /profile).
class ProfileEditScreen extends ConsumerWidget {
  const ProfileEditScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final profile = ref.watch(profileProvider);
    return Scaffold(
      appBar: AppBar(title: Text(t.t('settings.edit_profile', 'Edit profile'))),
      body: profile.when(
        loading: () => const Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
        error: (_, _) => Center(
          child: Text(t.t('settings.load_error', 'Could not load your profile.')),
        ),
        data: (p) => _ProfileForm(profile: p),
      ),
    );
  }
}

class _ProfileForm extends ConsumerStatefulWidget {
  final ProfileSettings profile;
  const _ProfileForm({required this.profile});

  @override
  ConsumerState<_ProfileForm> createState() => _ProfileFormState();
}

class _ProfileFormState extends ConsumerState<_ProfileForm> {
  late final TextEditingController _name;
  late final TextEditingController _email;
  late final TextEditingController _address;
  final _mapController = MapController();
  LatLng? _pin;
  late List<(TextEditingController, TextEditingController)> _contacts;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final p = widget.profile;
    _name = TextEditingController(text: p.name ?? '');
    _email = TextEditingController(text: p.email ?? '');
    _address = TextEditingController(text: p.address ?? '');
    _pin = (p.homeLat != null && p.homeLng != null)
        ? LatLng(p.homeLat!, p.homeLng!)
        : null;
    _contacts = p.additionalContacts
        .map((c) => (
              TextEditingController(text: c.label),
              TextEditingController(text: c.phone),
            ))
        .toList();
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _address.dispose();
    for (final (l, ph) in _contacts) {
      l.dispose();
      ph.dispose();
    }
    super.dispose();
  }

  void _addContact() => setState(() =>
      _contacts.add((TextEditingController(), TextEditingController())));

  void _removeContact(int i) {
    final (l, ph) = _contacts[i];
    l.dispose();
    ph.dispose();
    setState(() => _contacts.removeAt(i));
  }

  Future<void> _save() async {
    final t = ref.read(translatorProvider);
    // Keep only contacts with both a label and a phone.
    final contacts = <Map<String, String>>[];
    for (final (l, ph) in _contacts) {
      final label = l.text.trim();
      final phone = ph.text.trim();
      if (label.isNotEmpty && phone.isNotEmpty) {
        contacts.add({'label': label, 'phone': phone});
      }
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(settingsActionsProvider).saveProfile(
            name: _name.text.trim().isEmpty ? null : _name.text.trim(),
            email: _email.text.trim().isEmpty ? null : _email.text.trim(),
            address: _address.text.trim().isEmpty ? null : _address.text.trim(),
            homeLat: _pin?.latitude,
            homeLng: _pin?.longitude,
            additionalContacts: contacts,
          );
      if (mounted) Navigator.of(context).pop();
    } catch (_) {
      setState(() => _error =
          t.t('settings.save_error', 'Could not save. Please try again.'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    return ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          TextField(
            controller: _name,
            textCapitalization: TextCapitalization.words,
            decoration: InputDecoration(labelText: t.t('settings.name', 'Name')),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            decoration: InputDecoration(labelText: t.t('settings.email', 'Email')),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _address,
            maxLines: 2,
            decoration: InputDecoration(
              labelText: t.t('settings.address', 'Home address'),
              hintText: t.t('settings.address_hint', 'Building, street, area, city'),
            ),
          ),

          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(t.t('settings.home_location', 'Home location'),
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              if (_pin != null)
                TextButton.icon(
                  onPressed: () => setState(() => _pin = null),
                  icon: const Icon(Icons.clear, size: 16),
                  label: Text(t.t('settings.clear_pin', 'Clear')),
                ),
            ],
          ),
          Text(
            t.t('settings.tap_map_hint', 'Tap the map to drop a pin on your home.'),
            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: SizedBox(
              height: 220,
              child: FlutterMap(
                mapController: _mapController,
                options: MapOptions(
                  initialCenter: _pin ?? _fallbackCenter,
                  initialZoom: _pin != null ? 15 : 11,
                  onTap: (_, latlng) => setState(() => _pin = latlng),
                ),
                children: [
                  TileLayer(
                    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'com.izylrn.parent',
                  ),
                  if (_pin != null)
                    MarkerLayer(markers: [
                      Marker(
                        point: _pin!,
                        width: 44,
                        height: 44,
                        alignment: Alignment.topCenter,
                        child: const Icon(Icons.location_on,
                            color: Color(0xFFE11D48), size: 40),
                      ),
                    ]),
                ],
              ),
            ),
          ),
          if (_pin != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                '${_pin!.latitude.toStringAsFixed(5)}, ${_pin!.longitude.toStringAsFixed(5)}',
                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
              ),
            ),

          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(t.t('settings.additional_numbers', 'Additional numbers'),
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              TextButton.icon(
                onPressed: _contacts.length >= 10 ? null : _addContact,
                icon: const Icon(Icons.add, size: 18),
                label: Text(t.t('common.add', 'Add')),
              ),
            ],
          ),
          if (_contacts.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                t.t('settings.no_numbers', 'No extra numbers yet.'),
                style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
              ),
            ),
          for (int i = 0; i < _contacts.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  SizedBox(
                    width: 100,
                    child: TextField(
                      controller: _contacts[i].$1,
                      decoration: InputDecoration(
                        labelText: t.t('settings.label', 'Label'),
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      controller: _contacts[i].$2,
                      keyboardType: TextInputType.phone,
                      decoration: InputDecoration(
                        labelText: t.t('settings.number', 'Number'),
                        isDense: true,
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: () => _removeContact(i),
                    icon: const Icon(Icons.delete_outline),
                    tooltip: t.t('common.remove', 'Remove'),
                  ),
                ],
              ),
            ),

          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!,
                style: const TextStyle(
                    color: Colors.red, fontWeight: FontWeight.w500)),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _busy ? null : _save,
            child: _busy
                ? const SizedBox(
                    height: 22,
                    width: 22,
                    child: CircularProgressIndicator(
                        strokeWidth: 2.4, color: Colors.white))
                : Text(t.t('common.save', 'Save')),
          ),
        ],
      );
  }
}
