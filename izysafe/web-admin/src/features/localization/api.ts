/** Admin-only hooks for managing translations + dynamic menus (Sprint 11, F23). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/lib/api";

export interface TranslationRow {
  key: string;
  en: string;
  hi: string | null;
  ar: string | null;
  updated_at: string;
}

export interface MenuItemRow {
  id: string;
  item_key: string;
  label_key: string;
  icon: string | null;
  path: string;
  platform: "web" | "mobile";
  sort_order: number;
  visible: boolean;
  roles: string[];
}

// ------------------------------------------------------------ translations
export function useTranslations() {
  return useQuery({
    queryKey: ["localization"],
    queryFn: () => apiGet<TranslationRow[]>("/schools/localization"),
  });
}

/** Re-fetch the active-locale bundle so edits show up across the panel immediately. */
function useInvalidateI18n() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["localization"] });
    qc.invalidateQueries({ queryKey: ["i18n", "bundle"] });
  };
}

export function useCreateTranslation() {
  const invalidate = useInvalidateI18n();
  return useMutation({
    mutationFn: (body: { key: string; en: string; hi?: string | null; ar?: string | null }) =>
      apiPost<TranslationRow>("/schools/localization", body),
    onSuccess: () => {
      toast.success("Translation added");
      invalidate();
    },
  });
}

export function useUpdateTranslation() {
  const invalidate = useInvalidateI18n();
  return useMutation({
    mutationFn: ({ key, ...body }: { key: string; en: string; hi?: string | null; ar?: string | null }) =>
      apiPut<TranslationRow>(`/schools/localization/${encodeURIComponent(key)}`, body),
    onSuccess: () => {
      toast.success("Translation saved");
      invalidate();
    },
  });
}

export function useDeleteTranslation() {
  const invalidate = useInvalidateI18n();
  return useMutation({
    mutationFn: (key: string) => apiDelete(`/schools/localization/${encodeURIComponent(key)}`),
    onSuccess: () => {
      toast.success("Translation removed");
      invalidate();
    },
  });
}

// -------------------------------------------------------------------- menus
function useInvalidateMenu() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["menu-items"] });
    qc.invalidateQueries({ queryKey: ["menu", "nav"] });
  };
}

export function useMenuItems(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["menu-items"],
    queryFn: () => apiGet<MenuItemRow[]>("/schools/menu-items"),
    enabled: options?.enabled ?? true,
  });
}

export interface MenuItemInput {
  item_key: string;
  label_key: string;
  icon: string | null;
  path: string;
  sort_order?: number;
  visible?: boolean;
  roles: string[];
}

export function useCreateMenuItem() {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: (body: MenuItemInput) => apiPost<MenuItemRow>("/schools/menu-items", body),
    onSuccess: () => {
      toast.success("Menu item added");
      invalidate();
    },
  });
}

export function useUpdateMenuItem() {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Partial<MenuItemInput>) =>
      apiPatch<MenuItemRow>(`/schools/menu-items/${id}`, body),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteMenuItem() {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/schools/menu-items/${id}`),
    onSuccess: () => {
      toast.success("Menu item removed");
      invalidate();
    },
  });
}

export function useReorderMenu() {
  const invalidate = useInvalidateMenu();
  return useMutation({
    mutationFn: (ids: string[]) => apiPut<MenuItemRow[]>("/schools/menu-items/reorder", { ids }),
    onSuccess: () => invalidate(),
  });
}
