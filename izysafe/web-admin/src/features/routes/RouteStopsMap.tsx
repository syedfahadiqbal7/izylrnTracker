import { useEffect, useRef } from "react";
import L from "leaflet";
import {
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { Stop } from "./api";

const INDIA_CENTER: [number, number] = [20.5937, 78.9629];

function stopIcon(seq: number) {
  return L.divIcon({
    className: "",
    html: `<div style="width:26px;height:26px;border-radius:50%;background:#2C56EE;color:#fff;display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);font:600 12px/1 Inter,sans-serif">${seq}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -14],
  });
}

function ClickToAdd({ onAdd }: { onAdd: (lat: number, lng: number) => void }) {
  useMapEvents({ click: (e) => onAdd(e.latlng.lat, e.latlng.lng) });
  return null;
}

function FitStops({ points }: { points: [number, number][] }) {
  const map = useMap();
  const key = points.map((p) => p.join()).join("|");
  const prev = useRef("");
  useEffect(() => {
    if (key === prev.current || points.length === 0) return;
    prev.current = key;
    if (points.length === 1) map.setView(points[0], 14);
    else map.fitBounds(points, { padding: [50, 50] });
  }, [key, points, map]);
  return null;
}

export function RouteStopsMap({
  stops,
  onAddAt,
}: {
  stops: Stop[];
  onAddAt: (lat: number, lng: number) => void;
}) {
  const points = stops.map((s) => [s.lat, s.lng] as [number, number]);

  return (
    <MapContainer
      center={points[0] ?? INDIA_CENTER}
      zoom={points.length ? 13 : 5}
      // `isolate` contains Leaflet's internal z-indexes (panes/controls up to ~1000)
      // in their own stacking context so they never paint over modal dialogs (z-50).
      className="h-full w-full isolate"
      scrollWheelZoom
    >
      <TileLayer
        attribution='Tiles &copy; <a href="https://www.esri.com">Esri</a> &mdash; Source: Esri, HERE, Garmin, &copy; OpenStreetMap contributors'
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
      />
      <ClickToAdd onAdd={onAddAt} />
      <FitStops points={points} />

      {points.length > 1 && (
        <Polyline
          positions={points}
          pathOptions={{ color: "#2C56EE", weight: 3, opacity: 0.5 }}
        />
      )}
      {stops.map((s) => (
        <Marker key={s.id} position={[s.lat, s.lng]} icon={stopIcon(s.seq)}>
          <Popup>
            <b>Stop {s.seq}</b> — {s.name}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
