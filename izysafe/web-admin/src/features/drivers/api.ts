/** Driver management data hooks (school-admin side, /schools/drivers/*). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";

export interface Driver {
  id: string;
  school_id: string;
  name: string;
  phone: string | null;
  verified: boolean;
  active: boolean;
  has_access_code: boolean;
  last_login_at: string | null;
  created_at: string;
}

const KEY = ["drivers"];

export function useDrivers() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiGet<Driver[]>("/schools/drivers"),
  });
}

export interface CreateDriverInput {
  name: string;
  phone?: string;
  access_code?: string;
}

export function useCreateDriver() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateDriverInput) =>
      apiPost<Driver>("/schools/drivers", {
        name: input.name,
        phone: input.phone || null,
        access_code: input.access_code || null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useSetActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      apiPut<Driver>(`/schools/drivers/${id}`, { active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useSetDriverCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, access_code }: { id: string; access_code: string }) =>
      apiPost<Driver>(`/schools/drivers/${id}/set-code`, { access_code }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteDriver() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/schools/drivers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

/** A friendly, driver-typeable 6-digit access code. */
export function randomAccessCode(): string {
  let code = "";
  for (let i = 0; i < 6; i++) code += Math.floor(Math.random() * 10);
  return code;
}
