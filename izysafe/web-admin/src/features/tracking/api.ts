/** Live fleet tracking data hooks (school-admin side). */
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface FleetStop {
  id: string;
  name: string;
  lat: number;
  lng: number;
  seq: number;
}

export interface FleetBus {
  bus_id: string;
  bus_name: string;
  imei: string | null;
  traccar_id: number | null;
  online: boolean;
  last_seen: string | null;
  position: { lat: number; lng: number; timestamp: string | null } | null;
  route: {
    id: string;
    name: string;
    active: boolean;
    students: number;
    stops: FleetStop[];
  } | null;
  driver: { id: string; name: string } | null;
  trip: { active: boolean; started_at: string | null } | null;
}

/** Polls the live fleet on an interval so markers move on the map. */
export function useFleet(refetchMs = 10_000) {
  return useQuery({
    queryKey: ["fleet"],
    queryFn: () => apiGet<FleetBus[]>("/schools/buses/live"),
    refetchInterval: refetchMs,
    refetchOnWindowFocus: true,
  });
}

export interface LiveChild {
  child_id: string;
  child_name: string;
  class_grade: string | null;
  device_name: string | null;
  online: boolean;
  last_seen: string | null;
  battery: number | null;
  /** Within school hours/days — live position is only exposed when true. */
  in_window: boolean;
  position: { lat: number; lng: number; timestamp: string | null } | null;
}

/** Consented children's live positions (kid trackers). */
export function useChildrenFleet(refetchMs = 10_000) {
  return useQuery({
    queryKey: ["children-fleet"],
    queryFn: () => apiGet<LiveChild[]>("/schools/children/live"),
    refetchInterval: refetchMs,
    refetchOnWindowFocus: true,
  });
}

export interface RouteAssignment {
  id: string;
  route_id: string;
  child_id: string;
  child_name: string;
  stop_id: string | null;
}

/** The students assigned to a route (loaded when a bus is selected). */
export function useRouteAssignments(routeId: string | null) {
  return useQuery({
    queryKey: ["route-assignments", routeId],
    enabled: routeId !== null,
    queryFn: () =>
      apiGet<RouteAssignment[]>(`/schools/routes/${routeId}/assignments`),
  });
}
