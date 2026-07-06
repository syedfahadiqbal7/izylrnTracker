/** Routes, stops, assignments, and bus-device data hooks (school-admin). */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";

export interface Route {
  id: string;
  school_id: string;
  name: string;
  driver_id: string | null;
  device_id: string | null;
  active_from: string | null;
  active_to: string | null;
  active: boolean;
  created_at: string;
}

export interface Stop {
  id: string;
  route_id: string;
  name: string;
  lat: number;
  lng: number;
  seq: number;
  scheduled_at: string | null;
}

export interface Assignment {
  id: string;
  route_id: string;
  child_id: string;
  child_name: string;
  stop_id: string | null;
}

export interface BusDevice {
  id: string;
  school_id: string;
  name: string;
  imei: string;
  traccar_id: number | null;
  is_online: boolean;
  created_at: string;
}

/** Route/stop/assignment changes also affect the live map + fleet counts. */
function invalidateFleet(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: ["fleet"] });
}

// ------------------------------------------------------------------ routes
export function useRoutes() {
  return useQuery({
    queryKey: ["routes"],
    queryFn: () => apiGet<Route[]>("/schools/routes"),
  });
}

export interface RouteInput {
  name: string;
  driver_id?: string | null;
  device_id?: string | null;
  active?: boolean;
}

export function useCreateRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: RouteInput) => apiPost<Route>("/schools/routes", input),
    onSuccess: (r) => {
      toast.success(`Route "${r.name}" created`);
      qc.invalidateQueries({ queryKey: ["routes"] });
      invalidateFleet(qc);
    },
  });
}

export function useUpdateRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: RouteInput & { id: string }) =>
      apiPut<Route>(`/schools/routes/${id}`, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["routes"] });
      invalidateFleet(qc);
    },
  });
}

export function useDeleteRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/schools/routes/${id}`),
    onSuccess: () => {
      toast.success("Route deleted");
      qc.invalidateQueries({ queryKey: ["routes"] });
      invalidateFleet(qc);
    },
  });
}

// ------------------------------------------------------------------- stops
export function useStops(routeId: string | null) {
  return useQuery({
    queryKey: ["stops", routeId],
    enabled: routeId !== null,
    queryFn: () => apiGet<Stop[]>(`/schools/routes/${routeId}/stops`),
  });
}

export interface StopInput {
  name: string;
  lat: number;
  lng: number;
  seq: number;
}

function useStopMutation<TArgs>(fn: (a: TArgs) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stops"] });
      invalidateFleet(qc);
    },
  });
}

export const useAddStop = () =>
  useStopMutation(({ routeId, ...input }: StopInput & { routeId: string }) =>
    apiPost<Stop>(`/schools/routes/${routeId}/stops`, input),
  );

export const useUpdateStop = () =>
  useStopMutation(({ id, ...fields }: Partial<StopInput> & { id: string }) =>
    apiPut<Stop>(`/schools/stops/${id}`, fields),
  );

export const useDeleteStop = () =>
  useStopMutation((id: string) => apiDelete(`/schools/stops/${id}`));

export const useReorderStops = () =>
  useStopMutation(({ routeId, stop_ids }: { routeId: string; stop_ids: string[] }) =>
    apiPut<Stop[]>(`/schools/routes/${routeId}/stops/reorder`, { stop_ids }),
  );

// ------------------------------------------------------------- assignments
export function useAssignments(routeId: string | null) {
  return useQuery({
    queryKey: ["assignments", routeId],
    enabled: routeId !== null,
    queryFn: () => apiGet<Assignment[]>(`/schools/routes/${routeId}/assignments`),
  });
}

export function useAssignStudent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      routeId,
      enrollment_id,
      stop_id,
    }: {
      routeId: string;
      enrollment_id: string;
      stop_id?: string | null;
    }) =>
      apiPost<Assignment>(`/schools/routes/${routeId}/assignments`, {
        enrollment_id,
        stop_id: stop_id || null,
      }),
    onSuccess: (a) => {
      toast.success(`${a.child_name} assigned`);
      qc.invalidateQueries({ queryKey: ["assignments"] });
      invalidateFleet(qc);
    },
  });
}

export function useUnassign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assignmentId: string) =>
      apiDelete(`/schools/assignments/${assignmentId}`),
    onSuccess: () => {
      toast.success("Student removed from route");
      qc.invalidateQueries({ queryKey: ["assignments"] });
      invalidateFleet(qc);
    },
  });
}

// ------------------------------------------------------------ bus devices
export function useBuses() {
  return useQuery({
    queryKey: ["buses"],
    queryFn: () => apiGet<BusDevice[]>("/schools/buses"),
  });
}

export function useRegisterBus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      name: string;
      imei: string;
      traccar_id?: number | null;
    }) =>
      apiPost<BusDevice>("/schools/buses", {
        name: input.name,
        imei: input.imei,
        traccar_id: input.traccar_id ?? null,
      }),
    onSuccess: (b) => {
      toast.success(`Bus "${b.name}" registered`);
      qc.invalidateQueries({ queryKey: ["buses"] });
      invalidateFleet(qc);
    },
  });
}

export function useDeleteBus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/schools/buses/${id}`),
    onSuccess: () => {
      toast.success("Bus deleted");
      qc.invalidateQueries({ queryKey: ["buses"] });
      qc.invalidateQueries({ queryKey: ["routes"] });
      invalidateFleet(qc);
    },
  });
}
