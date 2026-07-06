/** Audit log data hooks (school-admin, admin-only). */
import { useQuery } from "@tanstack/react-query";
import { api, apiGetList } from "@/lib/api";
import type { ListMeta } from "@/types/api";

export interface AuditEntry {
  id: string;
  school_id: string | null;
  actor_type: string;
  actor_id: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditFilters {
  from?: string; // ISO datetime
  to?: string; // ISO datetime
  actor_type?: string;
  action?: string;
  entity_type?: string;
}

export interface AuditParams extends AuditFilters {
  limit: number;
  offset: number;
}

function toQuery(p: object): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(p)) {
    if (v !== undefined && v !== null && v !== "") out[k] = v as string | number;
  }
  return out;
}

export function useAudit(params: AuditParams) {
  return useQuery({
    queryKey: ["audit", params],
    queryFn: () =>
      apiGetList<AuditEntry[]>("/schools/audit", {
        params: toQuery(params),
      }) as Promise<{ items: AuditEntry[]; meta?: ListMeta }>,
    placeholderData: (prev) => prev,
  });
}

export async function downloadAuditCsv(filters: AuditFilters): Promise<void> {
  const resp = await api.get("/schools/audit/export", {
    params: toQuery(filters),
    responseType: "blob",
  });
  const url = URL.createObjectURL(resp.data as Blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "audit_log.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// --------------------------------------------------------------------------- //
// Readable labels
// --------------------------------------------------------------------------- //
export const ACTOR_LABELS: Record<string, string> = {
  school_admin: "Admin",
  driver: "Driver",
  parent: "Parent",
};

export const ACTION_LABELS: Record<string, string> = {
  "admin.login": "Admin signed in",
  "admin.create": "Staff / admin added",
  "admin.role_update": "Admin role / name updated",
  "admin.deactivate": "Admin deactivated",
  "admin.reactivate": "Admin reactivated",
  "admin.delete": "Admin deleted",
  "admin.password_change": "Password changed",
  "admin.password_reset": "Password reset",
  "school.config_update": "School settings updated",
  "enrollment.create": "Student enrolled",
  "enrollment.update": "Enrollment updated",
  "enrollment.remove": "Student removed",
  "enrollment.opt_in": "Parent granted consent",
  "enrollment.opt_out": "Parent withdrew consent",
  "attendance.manual_override": "Attendance overridden",
  "driver.login": "Driver signed in",
  "driver.create": "Driver added",
  "driver.set_code": "Driver access code set",
  "driver.trip.start": "Trip started",
  "driver.trip.end": "Trip ended",
  "driver.boarding": "Student boarded",
};

/** The curated set of actions offered in the filter dropdown. */
export const FILTERABLE_ACTIONS = Object.keys(ACTION_LABELS);
export const ENTITY_TYPES = [
  "enrollment",
  "child",
  "driver",
  "bus_trip",
  "school_admin",
  "school",
];

function prettify(s: string) {
  return s
    .replace(/[._]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export const actionLabel = (a: string) => ACTION_LABELS[a] ?? prettify(a);
export const actorLabel = (a: string) => ACTOR_LABELS[a] ?? prettify(a);
export const entityLabel = (e: string | null) => (e ? prettify(e) : "—");
