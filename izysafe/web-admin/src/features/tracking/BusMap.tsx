import { useEffect, useRef } from "react";
import L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { FleetBus } from "./api";

const INDIA_CENTER: [number, number] = [20.5937, 78.9629];

function busIcon(online: boolean, selected: boolean) {
  const color = online ? "#2C56EE" : "#94a3b8";
  const ring = selected
    ? "box-shadow:0 0 0 4px rgba(22,175,240,.55);"
    : "box-shadow:0 1px 4px rgba(0,0,0,.35);";
  return L.divIcon({
    className: "",
    html: `<div style="width:30px;height:30px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};display:flex;align-items:center;justify-content:center;border:2px solid #fff;${ring}">
      <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="transform:rotate(45deg)"><path d="M8 6v6"/><path d="M15 6v6"/><path d="M2 12h19.6"/><path d="M18 18h3s.8-1.7.8-2.8c0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3"/><circle cx="7" cy="18" r="2"/><path d="M9 18h5"/><circle cx="16" cy="18" r="2"/></svg>
    </div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 30],
    popupAnchor: [0, -28],
  });
}

function MapController({
  positions,
  focus,
}: {
  positions: [number, number][];
  focus: [number, number] | null;
}) {
  const map = useMap();
  const didFit = useRef(false);

  useEffect(() => {
    if (focus) map.flyTo(focus, Math.max(map.getZoom(), 14), { duration: 0.6 });
  }, [focus, map]);

  useEffect(() => {
    if (didFit.current || positions.length === 0) return;
    if (positions.length === 1) map.setView(positions[0], 14);
    else map.fitBounds(positions, { padding: [60, 60] });
    didFit.current = true;
  }, [positions, map]);

  return null;
}

export function BusMap({
  buses,
  selectedId,
  onSelect,
  trail,
}: {
  buses: FleetBus[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  trail: [number, number][];
}) {
  const located = buses.filter((b) => b.position);
  const positions = located.map(
    (b) => [b.position!.lat, b.position!.lng] as [number, number],
  );
  const selected = buses.find((b) => b.bus_id === selectedId) ?? null;
  const focus =
    selected?.position != null
      ? ([selected.position.lat, selected.position.lng] as [number, number])
      : null;
  const routeStops = selected?.route?.stops ?? [];

  return (
    <MapContainer
      center={positions[0] ?? INDIA_CENTER}
      zoom={positions.length ? 12 : 5}
      className="h-full w-full"
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapController positions={positions} focus={focus} />

      {/* Selected route: stops + a connecting line */}
      {routeStops.length > 1 && (
        <Polyline
          positions={routeStops.map((s) => [s.lat, s.lng] as [number, number])}
          pathOptions={{ color: "#2C56EE", weight: 3, opacity: 0.5 }}
        />
      )}
      {routeStops.map((s) => (
        <CircleMarker
          key={s.id}
          center={[s.lat, s.lng]}
          radius={6}
          pathOptions={{
            color: "#2C56EE",
            fillColor: "#fff",
            fillOpacity: 1,
            weight: 2,
          }}
        >
          <Popup>
            <b>Stop {s.seq}</b> — {s.name}
          </Popup>
        </CircleMarker>
      ))}

      {/* Live trail of the selected bus */}
      {trail.length > 1 && (
        <Polyline
          positions={trail}
          pathOptions={{
            color: "#16AFF0",
            weight: 3,
            opacity: 0.8,
            dashArray: "6 6",
          }}
        />
      )}

      {/* Bus markers */}
      {located.map((b) => (
        <Marker
          key={b.bus_id}
          position={[b.position!.lat, b.position!.lng]}
          icon={busIcon(b.online, b.bus_id === selectedId)}
          eventHandlers={{ click: () => onSelect(b.bus_id) }}
        >
          <Popup>
            <b>{b.bus_name}</b>
            <br />
            {b.route ? `Route: ${b.route.name}` : "No route"}
            <br />
            {b.driver ? `Driver: ${b.driver.name}` : "No driver"}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
