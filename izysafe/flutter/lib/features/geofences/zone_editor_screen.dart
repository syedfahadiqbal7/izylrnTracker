import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import '../../core/api_client.dart';
import '../../core/i18n.dart';
import '../../core/theme.dart';
import '../auth/auth_controller.dart';
import '../tracking/providers.dart' as tracking;
import 'models.dart';
import 'providers.dart';

const _fallbackCenter = LatLng(20.5937, 78.9629);
const _premiumTiers = {'premium', 'school'};

class ZoneEditorScreen extends ConsumerStatefulWidget {
  final String childId;
  final String? childName;
  final SafeZone? existing;
  const ZoneEditorScreen(
      {super.key, required this.childId, this.childName, this.existing});

  @override
  ConsumerState<ZoneEditorScreen> createState() => _ZoneEditorScreenState();
}

class _ZoneEditorScreenState extends ConsumerState<ZoneEditorScreen> {
  final _map = MapController();
  late final TextEditingController _name;

  late String _zoneType;
  late String _shape; // circle | polygon
  LatLng? _center;
  double _radius = 200;
  List<LatLng> _polygon = [];
  late String _color;
  late bool _notifyEnter;
  late bool _notifyExit;
  late bool _active;
  bool _saving = false;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final z = widget.existing;
    _name = TextEditingController(text: z?.name ?? '');
    _zoneType = z?.zoneType ?? 'other';
    _shape = z?.type ?? 'circle';
    _center = z?.center;
    _radius = (z?.radiusM ?? 200).toDouble().clamp(50, 2000);
    _polygon = List.of(z?.polygon ?? const []);
    _color = z?.color ?? zoneColors.first;
    _notifyEnter = z?.notifyEnter ?? true;
    _notifyExit = z?.notifyExit ?? true;
    _active = z?.active ?? true;
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  LatLng get _initialCenter =>
      _center ??
      (_polygon.isNotEmpty ? _polygon.first : null) ??
      ref.read(tracking.liveLocationProvider(widget.childId)).valueOrNull?.point ??
      _fallbackCenter;

  bool get _isPremium =>
      _premiumTiers.contains(ref.read(authControllerProvider).user?.subscriptionTier);

  void _onMapTap(LatLng p) {
    setState(() {
      if (_shape == 'circle') {
        _center = p;
      } else {
        _polygon = [..._polygon, p];
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    final color = parseHexColor(_color);

    return Scaffold(
      appBar: AppBar(
        title: Text(_isEdit
            ? t.t('zones.edit', 'Edit zone')
            : t.t('zones.new', 'New safe zone')),
        actions: [
          TextButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2.2))
                : Text(t.t('common.save', 'Save'),
                    style: const TextStyle(
                        color: Brand.indigo, fontWeight: FontWeight.w700)),
          ),
        ],
      ),
      body: Column(
        children: [
          SizedBox(
            height: 280,
            child: Stack(
              children: [
                FlutterMap(
                  mapController: _map,
                  options: MapOptions(
                    initialCenter: _initialCenter,
                    initialZoom: 15,
                    onTap: (_, p) => _onMapTap(p),
                  ),
                  children: [
                    TileLayer(
                      urlTemplate:
                          'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'com.izylrn.izysafe_parent',
                    ),
                    if (_shape == 'circle' && _center != null)
                      CircleLayer(circles: [
                        CircleMarker(
                          point: _center!,
                          radius: _radius,
                          useRadiusInMeter: true,
                          color: color.withValues(alpha: 0.15),
                          borderColor: color,
                          borderStrokeWidth: 2,
                        ),
                      ]),
                    if (_shape == 'polygon' && _polygon.length >= 2)
                      PolygonLayer(polygons: [
                        Polygon(
                          points: _polygon,
                          color: color.withValues(alpha: 0.15),
                          borderColor: color,
                          borderStrokeWidth: 2,
                        ),
                      ]),
                    MarkerLayer(markers: _markers(color)),
                  ],
                ),
                Positioned(
                  left: 12,
                  bottom: 12,
                  child: _MapHint(
                    text: _shape == 'circle'
                        ? t.t('zones.tap_center', 'Tap the map to set the centre')
                        : t.t('zones.tap_points', 'Tap the map to add points'),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              children: [
                TextField(
                  controller: _name,
                  decoration: InputDecoration(
                      labelText: t.t('zones.name', 'Zone name'),
                      hintText: t.t('zones.name_hint', 'e.g. Home, School')),
                ),
                const SizedBox(height: 18),
                _label(t.t('zones.type', 'Type')),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final zt in zoneTypes)
                      ChoiceChip(
                        selected: _zoneType == zt,
                        avatar: Icon(zoneTypeIcon(zt),
                            size: 16,
                            color: _zoneType == zt ? Colors.white : Brand.indigo),
                        label: Text(t.t('zonetype.$zt', _cap(zt))),
                        selectedColor: Brand.indigo,
                        labelStyle: TextStyle(
                            color: _zoneType == zt ? Colors.white : Brand.ink),
                        onSelected: (_) => setState(() => _zoneType = zt),
                      ),
                  ],
                ),
                const SizedBox(height: 18),
                _label(t.t('zones.shape', 'Shape')),
                Row(children: [
                  _ShapeButton(
                    label: t.t('zones.circle', 'Circle'),
                    icon: Icons.circle_outlined,
                    selected: _shape == 'circle',
                    onTap: () => setState(() => _shape = 'circle'),
                  ),
                  const SizedBox(width: 10),
                  _ShapeButton(
                    label: t.t('zones.polygon', 'Polygon'),
                    icon: Icons.pentagon_outlined,
                    selected: _shape == 'polygon',
                    locked: !_isPremium,
                    onTap: () {
                      if (!_isPremium) {
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                            content: Text(t.t('zones.polygon_premium',
                                'Polygon zones are a Premium feature.'))));
                        return;
                      }
                      setState(() => _shape = 'polygon');
                    },
                  ),
                ]),
                const SizedBox(height: 18),
                if (_shape == 'circle') ...[
                  Row(children: [
                    _label(t.t('zones.radius', 'Radius')),
                    const Spacer(),
                    Text('${_radius.round()} m',
                        style: const TextStyle(
                            fontWeight: FontWeight.w700, color: Brand.indigo)),
                  ]),
                  Slider(
                    value: _radius,
                    min: 50,
                    max: 2000,
                    divisions: 39,
                    activeColor: Brand.indigo,
                    label: '${_radius.round()} m',
                    onChanged: (v) => setState(() => _radius = v),
                  ),
                ] else ...[
                  Row(children: [
                    Text(
                        '${_polygon.length} ${t.t('zones.points', 'points')}',
                        style: TextStyle(color: Colors.grey.shade700)),
                    const Spacer(),
                    TextButton.icon(
                      onPressed: _polygon.isEmpty
                          ? null
                          : () => setState(() =>
                              _polygon = _polygon.sublist(0, _polygon.length - 1)),
                      icon: const Icon(Icons.undo, size: 18),
                      label: Text(t.t('zones.undo', 'Undo')),
                    ),
                    TextButton.icon(
                      onPressed: _polygon.isEmpty
                          ? null
                          : () => setState(() => _polygon = []),
                      icon: const Icon(Icons.clear, size: 18),
                      label: Text(t.t('zones.clear', 'Clear')),
                    ),
                  ]),
                ],
                const SizedBox(height: 10),
                _label(t.t('zones.color', 'Colour')),
                Row(
                  children: [
                    for (final c in zoneColors)
                      GestureDetector(
                        onTap: () => setState(() => _color = c),
                        child: Container(
                          margin: const EdgeInsetsDirectional.only(end: 10),
                          height: 30,
                          width: 30,
                          decoration: BoxDecoration(
                            color: parseHexColor(c),
                            shape: BoxShape.circle,
                            border: Border.all(
                                color: _color == c ? Brand.ink : Colors.transparent,
                                width: 2.5),
                          ),
                          child: _color == c
                              ? const Icon(Icons.check,
                                  color: Colors.white, size: 16)
                              : null,
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 8),
                _SectionCard(children: [
                  SwitchListTile(
                    value: _notifyEnter,
                    title: Text(t.t('zones.notify_enter', 'Alert on enter')),
                    subtitle: Text(t.t('zones.notify_enter_desc',
                        'Notify me when my child arrives.')),
                    onChanged: (v) => setState(() => _notifyEnter = v),
                  ),
                  const Divider(height: 1),
                  SwitchListTile(
                    value: _notifyExit,
                    title: Text(t.t('zones.notify_exit', 'Alert on exit')),
                    subtitle: Text(t.t('zones.notify_exit_desc',
                        'Notify me when my child leaves.')),
                    onChanged: (v) => setState(() => _notifyExit = v),
                  ),
                  const Divider(height: 1),
                  SwitchListTile(
                    value: _active,
                    title: Text(t.t('zones.active', 'Zone active')),
                    onChanged: (v) => setState(() => _active = v),
                  ),
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }

  List<Marker> _markers(Color color) {
    final markers = <Marker>[];
    if (_shape == 'circle' && _center != null) {
      markers.add(_dot(_center!, color));
    } else if (_shape == 'polygon') {
      for (final p in _polygon) {
        markers.add(_dot(p, color, small: true));
      }
    }
    return markers;
  }

  Marker _dot(LatLng p, Color color, {bool small = false}) => Marker(
        point: p,
        width: small ? 18 : 26,
        height: small ? 18 : 26,
        child: Container(
          decoration: BoxDecoration(
            color: Colors.white,
            shape: BoxShape.circle,
            border: Border.all(color: color, width: small ? 3 : 4),
          ),
        ),
      );

  Future<void> _save() async {
    final t = ref.read(translatorProvider);
    final name = _name.text.trim();
    if (name.isEmpty) {
      _snack(t.t('zones.name_required', 'Please name the zone.'));
      return;
    }
    final body = <String, dynamic>{
      'name': name,
      'zone_type': _zoneType,
      'type': _shape,
      'color': _color,
      'notify_enter': _notifyEnter,
      'notify_exit': _notifyExit,
      'active': _active,
    };
    if (_shape == 'circle') {
      if (_center == null) {
        _snack(t.t('zones.center_required', 'Tap the map to set the centre.'));
        return;
      }
      body['center_lat'] = _center!.latitude;
      body['center_lng'] = _center!.longitude;
      body['radius_m'] = _radius.round();
    } else {
      if (_polygon.length < 3) {
        _snack(t.t('zones.min_points', 'Add at least 3 points.'));
        return;
      }
      body['polygon_points'] = [
        for (final p in _polygon) {'lat': p.latitude, 'lng': p.longitude}
      ];
    }

    setState(() => _saving = true);
    try {
      final actions = ref.read(geofenceActionsProvider);
      if (_isEdit) {
        await actions.update(widget.childId, widget.existing!.id, body);
      } else {
        await actions.create(widget.childId, body);
      }
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (e) {
      _snack(e.message);
    } catch (_) {
      _snack(t.t('common.error_generic', 'Something went wrong. Please try again.'));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _snack(String msg) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    }
  }

  Widget _label(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(text,
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5)),
      );
}

String _cap(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

class _MapHint extends StatelessWidget {
  final String text;
  const _MapHint({required this.text});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.92),
          borderRadius: BorderRadius.circular(10),
          boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 6)],
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.touch_app, size: 15, color: Brand.indigo),
          const SizedBox(width: 6),
          Text(text,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        ]),
      );
}

class _ShapeButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool selected;
  final bool locked;
  final VoidCallback onTap;
  const _ShapeButton({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
    this.locked = false,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: selected ? Brand.indigo : Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
                color: selected ? Brand.indigo : const Color(0xFFE2E6F0)),
          ),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(locked ? Icons.lock_outline : icon,
                size: 18, color: selected ? Colors.white : Brand.ink),
            const SizedBox(width: 8),
            Text(label,
                style: TextStyle(
                    color: selected ? Colors.white : Brand.ink,
                    fontWeight: FontWeight.w600)),
          ]),
        ),
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  final List<Widget> children;
  const _SectionCard({required this.children});
  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFFEBEEF6)),
        ),
        child: Column(children: children),
      );
}
