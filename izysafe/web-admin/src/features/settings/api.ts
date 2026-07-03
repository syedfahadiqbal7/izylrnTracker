/** Settings data hooks: school config update + admin/staff management. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/lib/api";
import type { School } from "@/features/school/api";

export type AdminRole = "admin" | "staff";

export interface SchoolAdminRow {
  id: string;
  school_id: string;
  email: string;
  name: string | null;
  role: AdminRole;
  active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface SchoolUpdate {
  name?: string;
  address?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  timezone?: string;
  holidays?: string[];
  on_time_before?: string;
  late_until?: string;
  arrival_window_from?: string;
  day_ends_at?: string;
}

export function useUpdateSchool() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: SchoolUpdate) => apiPut<School>("/schools/me", input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["school-me"] }),
  });
}

// -------------------------------------------------------------- my account
export function useUpdateMyName() {
  return useMutation({
    mutationFn: (name: string) => apiPatch("/schools/admins/me", { name }),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      apiPost("/schools/admins/me/password", body),
  });
}

// ------------------------------------------------------- admins & staff
export function useAdmins() {
  return useQuery({
    queryKey: ["admins"],
    queryFn: () => apiGet<SchoolAdminRow[]>("/schools/admins"),
  });
}

export function useInviteStaff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      email: string;
      password: string;
      name?: string;
      role: AdminRole;
    }) => apiPost<SchoolAdminRow>("/schools/admins", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admins"] }),
  });
}

export function useManageAdmin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      role?: AdminRole;
      name?: string;
    }) => apiPatch<SchoolAdminRow>(`/schools/admins/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admins"] }),
  });
}

export function useSetAdminActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      apiPost<SchoolAdminRow>(
        `/schools/admins/${id}/${active ? "reactivate" : "deactivate"}`,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admins"] }),
  });
}

export function useDeleteAdmin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/schools/admins/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admins"] }),
  });
}
