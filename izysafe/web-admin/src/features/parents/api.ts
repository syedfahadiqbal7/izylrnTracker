/** Parents data hooks (Model 1, school-admin side, /schools/parents/*). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGetList, apiPut } from "@/lib/api";
import type { ListMeta } from "@/types/api";

export interface ParentChild {
  name: string;
  class_grade: string | null;
  parent_opt_in: boolean;
  location_opt_in: boolean;
}

export interface Parent {
  id: string;
  name: string | null;
  phone: string;
  last_login_at: string | null;
  child_count: number;
  children: ParentChild[];
}

export interface ParentsParams {
  q?: string;
  limit: number;
  offset: number;
}

export function useParents(params: ParentsParams) {
  return useQuery({
    queryKey: ["parents", params],
    queryFn: () =>
      apiGetList<Parent[]>("/schools/parents", {
        params: {
          q: params.q || undefined,
          limit: params.limit,
          offset: params.offset,
        },
      }) as Promise<{ items: Parent[]; meta?: ListMeta }>,
    placeholderData: (prev) => prev,
  });
}

export function useUpdateParent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string | null }) =>
      apiPut(`/schools/parents/${id}`, { name }),
    onSuccess: () => {
      toast.success("Parent updated");
      qc.invalidateQueries({ queryKey: ["parents"] });
    },
  });
}

export function useRemoveParent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/schools/parents/${id}`),
    onSuccess: () => {
      toast.success("Parent removed from school");
      qc.invalidateQueries({ queryKey: ["parents"] });
      qc.invalidateQueries({ queryKey: ["roster"] });
    },
  });
}
