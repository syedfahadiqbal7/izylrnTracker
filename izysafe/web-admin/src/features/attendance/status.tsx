import { Badge } from "@/components/ui/badge";
import type { AttendanceStatus } from "./types";

type Variant = "success" | "warning" | "destructive" | "muted";

export const STATUS_META: Record<
  AttendanceStatus,
  { label: string; variant: Variant }
> = {
  on_time: { label: "On time", variant: "success" },
  late: { label: "Late", variant: "warning" },
  early: { label: "Early", variant: "muted" },
  absent: { label: "Absent", variant: "destructive" },
  unknown: { label: "No record", variant: "muted" },
};

export const STATUS_ORDER: AttendanceStatus[] = [
  "on_time",
  "late",
  "early",
  "absent",
  "unknown",
];

/** Statuses an admin can assign via manual override (not the derived "unknown"). */
export const OVERRIDE_STATUSES: AttendanceStatus[] = [
  "on_time",
  "late",
  "early",
  "absent",
];

export function rateVariant(rate: number): Variant {
  if (rate >= 0.9) return "success";
  if (rate >= 0.75) return "warning";
  return "destructive";
}

export function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[status as AttendanceStatus] ?? {
    label: status,
    variant: "muted" as const,
  };
  return <Badge variant={meta.variant}>{meta.label}</Badge>;
}
