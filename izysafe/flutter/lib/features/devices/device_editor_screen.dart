import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/i18n.dart';
import '../../core/language_button.dart';
import '../../core/theme.dart';
import '../geofences/models.dart' show zoneColors, parseHexColor;
import 'models.dart';
import 'providers.dart';

/// Pair a new device (full form) or edit an existing one (name / colour / model +
/// battery + watch-removed settings). IMEI and type are fixed once paired.
class DeviceEditorScreen extends ConsumerStatefulWidget {
  final String childId;
  final String? childName;
  final Device? existing;
  const DeviceEditorScreen({
    super.key,
    required this.childId,
    this.childName,
    this.existing,
  });

  @override
  ConsumerState<DeviceEditorScreen> createState() => _DeviceEditorScreenState();
}

class _DeviceEditorScreenState extends ConsumerState<DeviceEditorScreen> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _imei;
  late final TextEditingController _model;
  late String _type;
  late String? _color;
  late int _batteryThreshold;
  late bool _watchRemovedEnabled;
  late int _removedThreshold;
  late bool _active;
  bool _saving = false;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final d = widget.existing;
    _name = TextEditingController(text: d?.name ?? '');
    _imei = TextEditingController(text: d?.imei ?? '');
    _model = TextEditingController(text: d?.model ?? '');
    _type = d?.deviceType ?? 'watch';
    _color = d?.color;
    _batteryThreshold = d?.batteryThreshold ?? 20;
    _watchRemovedEnabled = d?.watchRemovedEnabled ?? false;
    _removedThreshold = d?.watchRemovedThresholdMin ?? 10;
    _active = d?.active ?? true;
  }

  @override
  void dispose() {
    _name.dispose();
    _imei.dispose();
    _model.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Text(
          _isEdit
              ? t.t('devices.edit', 'Edit device')
              : t.t('devices.new', 'Pair a device'),
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18),
        ),
        actions: const [LanguageButton(), SizedBox(width: 4)],
      ),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 110),
          children: [
            // ----- Name
            TextFormField(
              controller: _name,
              textCapitalization: TextCapitalization.words,
              decoration: InputDecoration(
                labelText: t.t('devices.name', 'Device name'),
                hintText: t.t('devices.name_hint', "e.g. Aryan's Watch"),
                prefixIcon: const Icon(Icons.badge_outlined),
              ),
              validator: (v) => (v == null || v.trim().isEmpty)
                  ? t.t('devices.name_required', 'Please name the device.')
                  : null,
            ),
            const SizedBox(height: 14),

            // ----- IMEI (immutable once paired)
            TextFormField(
              controller: _imei,
              enabled: !_isEdit,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(
                labelText: t.t('devices.imei', 'IMEI'),
                hintText: t.t('devices.imei_hint',
                    'Enter or scan the IMEI printed on the device.'),
                prefixIcon: const Icon(Icons.qr_code_2_rounded),
              ),
              validator: (v) {
                if (_isEdit) return null;
                if (v == null || v.trim().length < 5) {
                  return t.t('devices.imei_required', 'Please enter the device IMEI.');
                }
                return null;
              },
            ),
            const SizedBox(height: 18),

            // ----- Type (fixed once paired)
            Text(t.t('devices.type', 'Device type'),
                style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                for (final dt in deviceTypes)
                  ChoiceChip(
                    avatar: Icon(deviceTypeIcon(dt),
                        size: 18,
                        color: _type == dt ? Colors.white : Brand.indigo),
                    label: Text(deviceTypeLabel(t, dt)),
                    selected: _type == dt,
                    selectedColor: Brand.indigo,
                    labelStyle: TextStyle(
                        color: _type == dt ? Colors.white : Brand.ink,
                        fontWeight: FontWeight.w600),
                    onSelected: _isEdit ? null : (_) => setState(() => _type = dt),
                  ),
              ],
            ),
            const SizedBox(height: 18),

            // ----- Model (optional)
            TextFormField(
              controller: _model,
              decoration: InputDecoration(
                labelText: t.t('devices.model', 'Model'),
                prefixIcon: const Icon(Icons.info_outline_rounded),
              ),
            ),
            const SizedBox(height: 18),

            // ----- Colour
            Text(t.t('devices.color', 'Colour'),
                style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 10,
              children: [
                for (final hex in zoneColors)
                  GestureDetector(
                    onTap: () => setState(() => _color = hex),
                    child: Container(
                      height: 34,
                      width: 34,
                      decoration: BoxDecoration(
                        color: parseHexColor(hex),
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: _color == hex ? Brand.ink : Colors.transparent,
                          width: 3,
                        ),
                      ),
                    ),
                  ),
              ],
            ),

            // ----- Edit-only: battery + watch-removed + active
            if (_isEdit) ...[
              const Divider(height: 34),
              _dropdownRow(
                t.t('devices.battery_threshold', 'Low-battery alert at'),
                _batteryThreshold,
                batteryThresholds,
                (v) => setState(() => _batteryThreshold = v),
                suffix: '%',
              ),
              if (_type == 'watch') ...[
                const SizedBox(height: 6),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(t.t('devices.watch_removed', 'Watch-removed alert')),
                  subtitle: Text(t.t('devices.watch_removed_desc',
                      'Alert me if the watch is taken off.')),
                  value: _watchRemovedEnabled,
                  onChanged: (v) => setState(() => _watchRemovedEnabled = v),
                ),
                if (_watchRemovedEnabled)
                  _dropdownRow(
                    t.t('devices.removed_threshold', 'Alert after'),
                    _removedThreshold,
                    removedThresholds,
                    (v) => setState(() => _removedThreshold = v),
                    suffix: ' ${t.t('devices.minutes', 'min')}',
                  ),
              ],
              const SizedBox(height: 6),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(t.t('devices.active', 'Active')),
                value: _active,
                onChanged: (v) => setState(() => _active = v),
              ),
            ] else ...[
              const SizedBox(height: 20),
              _InfoNote(
                text: t.t('devices.pending_hint',
                    'Live tracking starts once the device powers on and connects.'),
              ),
            ],
          ],
        ),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
      floatingActionButton: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: Brand.indigo,
              padding: const EdgeInsets.symmetric(vertical: 15),
            ),
            icon: _saving
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2.4, color: Colors.white))
                : Icon(_isEdit ? Icons.save_rounded : Icons.link_rounded),
            label: Text(_saving
                ? (_isEdit
                    ? t.t('common.saving', 'Saving…')
                    : t.t('devices.pairing', 'Pairing…'))
                : (_isEdit
                    ? t.t('devices.save', 'Save')
                    : t.t('devices.add', 'Add device'))),
            onPressed: _saving ? null : _submit,
          ),
        ),
      ),
    );
  }

  Widget _dropdownRow(
    String label,
    int value,
    List<int> options,
    ValueChanged<int> onChanged, {
    String suffix = '',
  }) {
    return Row(
      children: [
        Expanded(child: Text(label)),
        DropdownButton<int>(
          value: value,
          items: [
            for (final o in options)
              DropdownMenuItem(value: o, child: Text('$o$suffix')),
          ],
          onChanged: (v) => v == null ? null : onChanged(v),
        ),
      ],
    );
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _saving = true);
    final t = ref.read(translatorProvider);
    final actions = ref.read(deviceActionsProvider);
    try {
      if (_isEdit) {
        final body = <String, dynamic>{
          'name': _name.text.trim(),
          'model': _model.text.trim().isEmpty ? null : _model.text.trim(),
          'color': _color,
          'battery_threshold': _batteryThreshold,
          'watch_removed_enabled': _watchRemovedEnabled,
          'watch_removed_threshold_min': _removedThreshold,
          'active': _active,
        };
        await actions.update(widget.childId, widget.existing!.id, body);
      } else {
        final body = <String, dynamic>{
          'name': _name.text.trim(),
          'imei': _imei.text.trim(),
          'device_type': _type,
          if (_model.text.trim().isNotEmpty) 'model': _model.text.trim(),
          if (_color != null) 'color': _color,
        };
        await actions.add(widget.childId, body);
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(_isEdit
                ? t.t('common.saved', 'Saved')
                : t.t('devices.paired', 'Device paired'))));
        Navigator.of(context).pop();
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class _InfoNote extends StatelessWidget {
  final String text;
  const _InfoNote({required this.text});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFFEFF2FB),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(children: [
          const Icon(Icons.info_outline_rounded, size: 18, color: Brand.indigo),
          const SizedBox(width: 10),
          Expanded(
              child: Text(text,
                  style: const TextStyle(fontSize: 12.5, color: Brand.ink))),
        ]),
      );
}
