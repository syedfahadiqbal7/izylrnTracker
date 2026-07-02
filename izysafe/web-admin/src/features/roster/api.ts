/** Roster / enrollment data hooks (school-admin side, /schools/students/*). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGetList, apiPatch, apiPost } from "@/lib/api";
import type { ListMeta } from "@/types/api";

export interface Enrollment {
  id: string;
  school_id: string;
  child_id: string;
  child_name: string;
  class_grade: string | null;
  parent_name: string | null;
  parent_phone: string | null;
  parent_opt_in: boolean;
  bus_opt_in: boolean;
  enrolled_at: string;
}

export interface RosterParams {
  q?: string;
  class_grade?: string;
  opted_in?: boolean;
  limit: number;
  offset: number;
}

export function useRoster(params: RosterParams) {
  return useQuery({
    queryKey: ["roster", params],
    queryFn: () =>
      apiGetList<Enrollment[]>("/schools/students", {
        params: {
          q: params.q || undefined,
          class_grade: params.class_grade || undefined,
          opted_in: params.opted_in,
          limit: params.limit,
          offset: params.offset,
        },
      }) as Promise<{ items: Enrollment[]; meta?: ListMeta }>,
    placeholderData: (prev) => prev, // keep the table steady while paging/searching
  });
}

export interface EnrollInput {
  phone: string;
  child_name?: string;
  class_grade?: string;
}

export function useEnrollStudent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: EnrollInput) =>
      apiPost<Enrollment>("/schools/students", {
        phone: input.phone,
        child_name: input.child_name || null,
        class_grade: input.class_grade || null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roster"] }),
  });
}

export function useUpdateEnrollment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, class_grade }: { id: string; class_grade: string | null }) =>
      apiPatch<Enrollment>(`/schools/students/${id}`, { class_grade }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roster"] }),
  });
}

export function useRemoveEnrollment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/schools/students/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roster"] }),
  });
}
