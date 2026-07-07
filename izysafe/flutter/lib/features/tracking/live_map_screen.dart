import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/i18n.dart';
import '../../core/language_button.dart';
import '../../core/theme.dart';
import '../auth/auth_controller.dart';
import '../children/child.dart';
import 'models.dart';
import 'providers.dart';

/// Fallback map center when nothing has a position yet (geographic centroid of India).
const _fallbackCenter = LatLng(20.5937, 78.9629);

class LiveMapScreen extends ConsumerStatefulWidget {
  final String childId;
  final Child? child;
  const LiveMapScreen({super.key, required this.childId, this.child});

  @override
  ConsumerState<LiveMapScreen> createState() => _LiveMapScreenState();
}

class _LiveMapScreenState extends ConsumerState<LiveMapScreen> {
  final _map = MapController();
  bool _didAutoCenter = false;

  void _center(LatLng p, {double zoom = 16}) {
    _map.move(p, zoom);
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    final childId = widget.childId;
    final location = ref.watch(liveLocationProvider(childId));
    final geofences = ref.watch(geofencesProvider(childId)).valueOrNull ?? const [];
    final bus = ref.watch(busProvider(childId)).valueOrNull;
    final sosList = ref.watch(activeSosProvider).valueOrNull ?? const [];
    final sos = sosList.where((s) => s.childId == childId).firstOrNull;

    final loc = location.valueOrNull;

    // Auto-center on the child's first fix.
    ref.listen(liveLocationProvider(childId), (_, next) {
      final p = next.valueOrNull;
      if (p != null && !_didAutoCenter) {
        _didAutoCenter = true;
        WidgetsBinding.instance.addPostFrameCallback((_) => _center(p.point));
      }
    });

    final initialCenter = loc?.point ??
        sos?.point ??
        geofences.map((g) => g.center).whereType<LatLng>().firstOrNull ??
        bus?.point ??
        _fallbackCenter;

    return Scaffold(
      body: Stack(
        children: [
          FlutterMap(
            mapController: _map,
            options: MapOptions(
              initialCenter: initialCenter,
              initialZoom: loc != null ? 16 : 5,
              minZoom: 3,
              maxZoom: 18,
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.izylrn.izysafe_parent',
              ),
              // Geofence fills + borders (circles).
              CircleLayer(
                circles: [
                  for (final g in geofences)
                    if (g.isCircle)
                      CircleMarker(
                        point: g.center!,
                        radius: g.radiusM!.toDouble(),
                        useRadiusInMeter: true,
                        color: g.color.withValues(alpha: 0.12),
                        borderColor: g.color.withValues(alpha: 0.8),
                        borderStrokeWidth: 2,
                      ),
                ],
              ),
              // Geofence polygons.
              PolygonLayer(
                polygons: [
                  for (final g in geofences)
                    if (g.isPolygon)
                      Polygon(
                        points: g.polygon,
                        color: g.color.withValues(alpha: 0.12),
                        borderColor: g.color.withValues(alpha: 0.8),
                        borderStrokeWidth: 2,
                      ),
                ],
              ),
              MarkerLayer(markers: _markers(t, loc, bus, sos)),
            ],
          ),

          // Top bar (over the map).
          _TopBar(
            title: widget.child?.name ?? t.t('map.title', 'Live Location'),
            childId: childId,
            child: widget.child,
          ),

          // SOS banner.
          if (sos != null)
            Positioned(
              left: 12,
              right: 12,
              top: MediaQuery.of(context).padding.top + 64,
              child: _SosBanner(sos: sos, childName: widget.child?.name),
            ),

          // Bottom info sheet.
          Positioned(
            left: 12,
            right: 12,
            bottom: 12,
            child: _InfoSheet(
              location: loc,
              locationLoading: location.isLoading && loc == null,
              bus: bus,
              geofenceCount: geofences.length,
              onManageZones: () =>
                  context.push('/child/$childId/zones', extra: widget.child),
            ),
          ),
        ],
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.startFloat,
      floatingActionButton: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          FloatingActionButton.small(
            heroTag: 'recenter',
            backgroundColor: Colors.white,
            foregroundColor: Brand.indigo,
            tooltip: t.t('map.recenter', 'Recenter'),
            onPressed: loc != null ? () => _center(loc.point) : null,
            child: const Icon(Icons.my_location),
          ),
          const SizedBox(height: 10),
          FloatingActionButton.extended(
            heroTag: 'sos',
            backgroundColor: const Color(0xFFE11D48),
            foregroundColor: Colors.white,
            icon: const Icon(Icons.emergency_share),
            label: Text(t.t('emergency.button', 'Emergency')),
            onPressed: () => _openEmergencySheet(context, t),
          ),
        ],
      ),
    );
  }

  List<Marker> _markers(
      Translator t, LiveLocation? loc, BusLive? bus, SosEvent? sos) {
    final markers = <Marker>[];

    // Bus marker.
    if (bus?.point != null) {
      markers.add(Marker(
        point: bus!.point!,
        width: 42,
        height: 42,
        child: _Pin(icon: Icons.directions_bus, color: Brand.cyan),
      ));
    }

    // Child marker (red when an SOS is active).
    final childPoint = loc?.point ?? sos?.point;
    if (childPoint != null) {
      final emergency = sos != null;
      markers.add(Marker(
        point: childPoint,
        width: 48,
        height: 48,
        child: _Pin(
          icon: emergency ? Icons.warning_amber_rounded : Icons.person_pin_circle,
          color: emergency ? const Color(0xFFE11D48) : Brand.violet,
          pulsing: emergency,
        ),
      ));
    }
    return markers;
  }

  Future<void> _openEmergencySheet(BuildContext context, Translator t) async {
    final user = ref.read(authControllerProvider).user;
    final number = _emergencyNumber(user?.countryCode);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 8),
              child: Text(t.t('emergency.title', 'Emergency options'),
                  style: const TextStyle(
                      fontSize: 17, fontWeight: FontWeight.w700)),
            ),
            ListTile(
              leading: const CircleAvatar(
                backgroundColor: Color(0xFFFDE7EC),
                child: Icon(Icons.local_phone, color: Color(0xFFE11D48)),
              ),
              title: Text(t.t('emergency.call_services', 'Call emergency services')),
              subtitle: Text(number),
              onTap: () async {
                Navigator.pop(ctx);
                await _confirmAndCall(context, t, number);
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmAndCall(
      BuildContext context, Translator t, String number) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t.t('emergency.button', 'Emergency')),
        content: Text(t.t('emergency.confirm',
            'This will place a phone call. Continue?')),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: Text(t.t('common.cancel', 'Cancel'))),
          FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFE11D48)),
              onPressed: () => Navigator.pop(ctx, true),
              child: Text('${t.t('common.call', 'Call')} $number')),
        ],
      ),
    );
    if (ok == true) {
      final uri = Uri(scheme: 'tel', path: number);
      if (await canLaunchUrl(uri)) await launchUrl(uri);
    }
  }
}

String _emergencyNumber(String? countryCode) {
  switch (countryCode) {
    case '+971':
      return '999'; // UAE police
    case '+91':
    default:
      return '112'; // India all-in-one emergency
  }
}

// --------------------------------------------------------------------------- //
// Pieces
// --------------------------------------------------------------------------- //
class _Pin extends StatelessWidget {
  final IconData icon;
  final Color color;
  final bool pulsing;
  const _Pin({required this.icon, required this.color, this.pulsing = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        shape: BoxShape.circle,
        border: Border.all(color: color, width: 3),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: pulsing ? 0.5 : 0.25),
            blurRadius: pulsing ? 14 : 8,
            spreadRadius: pulsing ? 2 : 0,
          ),
        ],
      ),
      alignment: Alignment.center,
      child: Icon(icon, color: color, size: 22),
    );
  }
}

class _TopBar extends ConsumerWidget {
  final String title;
  final String childId;
  final Child? child;
  const _TopBar({required this.title, required this.childId, this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return Positioned(
      left: 12,
      right: 12,
      top: MediaQuery.of(context).padding.top + 8,
      child: Material(
        elevation: 3,
        borderRadius: BorderRadius.circular(16),
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
          child: Row(
            children: [
              IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: () => Navigator.of(context).maybePop(),
              ),
              Expanded(
                child: Text(title,
                    style: const TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 16),
                    overflow: TextOverflow.ellipsis),
              ),
              IconButton(
                tooltip: t.t('devices.title', 'Devices'),
                icon: const Icon(Icons.watch_rounded),
                onPressed: () =>
                    context.push('/child/$childId/devices', extra: child),
              ),
              IconButton(
                tooltip: t.t('share.title', 'Share links'),
                icon: const Icon(Icons.share_location_rounded),
                onPressed: () =>
                    context.push('/child/$childId/share', extra: child),
              ),
              IconButton(
                tooltip: t.t('chat.title', 'Chat'),
                icon: const Icon(Icons.chat_bubble_outline_rounded),
                onPressed: () =>
                    context.push('/child/$childId/chat', extra: child),
              ),
              const LanguageButton(),
            ],
          ),
        ),
      ),
    );
  }
}

class _SosBanner extends ConsumerStatefulWidget {
  final SosEvent sos;
  final String? childName;
  const _SosBanner({required this.sos, this.childName});

  @override
  ConsumerState<_SosBanner> createState() => _SosBannerState();
}

class _SosBannerState extends ConsumerState<_SosBanner> {
  bool _resolving = false;

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    return Material(
      elevation: 4,
      borderRadius: BorderRadius.circular(16),
      color: const Color(0xFFE11D48),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Icon(Icons.crisis_alert, color: Colors.white),
              const SizedBox(width: 10),
              Expanded(
                child: Text(t.t('sos.active_title', 'SOS Emergency'),
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        fontSize: 16)),
              ),
            ]),
            const SizedBox(height: 6),
            Text(
              '${widget.childName ?? widget.sos.childName ?? ''} ${t.t('sos.active_body', 'triggered an emergency alert.')}'
                  .trim(),
              style: const TextStyle(color: Colors.white),
            ),
            if (widget.sos.approximate)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('· ${t.t('sos.approximate', 'Approximate location')}',
                    style: const TextStyle(color: Colors.white70, fontSize: 12)),
              ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: const Color(0xFFE11D48),
                ),
                onPressed: _resolving
                    ? null
                    : () async {
                        setState(() => _resolving = true);
                        try {
                          await ref.read(resolveSosProvider)(widget.sos.id);
                        } finally {
                          if (mounted) setState(() => _resolving = false);
                        }
                      },
                child: Text(_resolving
                    ? t.t('sos.resolving', 'Resolving…')
                    : t.t('sos.resolve', 'Resolve emergency')),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoSheet extends ConsumerWidget {
  final LiveLocation? location;
  final bool locationLoading;
  final BusLive? bus;
  final int geofenceCount;
  final VoidCallback onManageZones;
  const _InfoSheet({
    required this.location,
    required this.locationLoading,
    required this.bus,
    required this.geofenceCount,
    required this.onManageZones,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    return Material(
      elevation: 4,
      borderRadius: BorderRadius.circular(18),
      color: Colors.white,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Container(
                height: 40,
                width: 40,
                decoration: BoxDecoration(
                  gradient: Brand.gradient,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.my_location, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(t.t('map.title', 'Live Location'),
                        style: const TextStyle(
                            fontWeight: FontWeight.w700, fontSize: 15)),
                    const SizedBox(height: 2),
                    Text(_status(t),
                        style: TextStyle(
                            color: Colors.grey.shade600, fontSize: 12.5)),
                  ],
                ),
              ),
              _SafeZonesChip(
                  count: geofenceCount,
                  label: t.t('map.safe_zones', 'Safe zones'),
                  onTap: onManageZones),
            ]),
            if (location == null && !locationLoading)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                    t.t('map.no_location_hint',
                        'The tracker will appear here once it reports a position.'),
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 12.5)),
              ),
            if (bus != null) ...[
              const Divider(height: 22),
              _BusRow(bus: bus!),
            ],
          ],
        ),
      ),
    );
  }

  String _status(Translator t) {
    if (location != null) {
      return '${t.t('map.last_seen', 'Last seen')} · ${_ago(location!.timestamp, t)}';
    }
    if (locationLoading) return t.t('map.locating', 'Locating…');
    return t.t('map.no_location', 'No live location yet');
  }
}

class _SafeZonesChip extends StatelessWidget {
  final int count;
  final String label;
  final VoidCallback onTap;
  const _SafeZonesChip(
      {required this.count, required this.label, required this.onTap});
  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: const Color(0xFFEFF2FB),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(children: [
          Row(mainAxisSize: MainAxisSize.min, children: [
            Text('$count',
                style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    color: Brand.indigo,
                    fontSize: 15)),
            const Icon(Icons.chevron_right, size: 15, color: Brand.indigo),
          ]),
          Text(label,
              style: const TextStyle(color: Brand.indigo, fontSize: 10.5)),
        ]),
      ),
    );
  }
}

class _BusRow extends ConsumerWidget {
  final BusLive bus;
  const _BusRow({required this.bus});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final eta = bus.etaMinutes;
    return Row(
      children: [
        const CircleAvatar(
          radius: 18,
          backgroundColor: Color(0xFFE7F6FE),
          child: Icon(Icons.directions_bus, color: Brand.cyan, size: 18),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${t.t('bus.title', 'School Bus')} · ${bus.routeName}',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
              const SizedBox(height: 2),
              Text(
                bus.hasPosition
                    ? [
                        if (bus.stopName != null)
                          '${t.t('bus.stop', 'Stop')}: ${bus.stopName}',
                        t.t('bus.en_route', 'En route'),
                      ].join(' · ')
                    : t.t('bus.no_position', 'Bus position not available yet.'),
                style: TextStyle(color: Colors.grey.shade600, fontSize: 12.5),
              ),
            ],
          ),
        ),
        if (eta != null)
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('${eta.round()}',
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 18, color: Brand.cyan)),
              Text('${t.t('bus.eta', 'ETA')} ${t.t('bus.min', 'min')}',
                  style: TextStyle(color: Colors.grey.shade600, fontSize: 10.5)),
            ],
          ),
      ],
    );
  }
}

String _ago(DateTime? ts, Translator t) {
  if (ts == null) return t.t('map.moments_ago', 'moments ago');
  final d = DateTime.now().difference(ts);
  if (d.inMinutes < 1) return t.t('map.moments_ago', 'moments ago');
  if (d.inMinutes < 60) return '${d.inMinutes} ${t.t('map.min_ago', 'min ago')}';
  if (d.inHours < 24) return '${d.inHours} ${t.t('map.hr_ago', 'hr ago')}';
  return '${d.inDays}d';
}
