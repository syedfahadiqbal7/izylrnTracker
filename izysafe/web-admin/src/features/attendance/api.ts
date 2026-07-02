/** Data hooks + calls for attendance reporting (Sprint 10 backend). */
import { useQuery } from "@tanstack/react-query";
import { api, apiGet, apiGetList } from "@/lib/api";
import type { AttendanceReport, ReportParams } from "./types";

interface RosterRow {
  class_grade: string | null;
}

/** GET /schools/attendance/report — date-range summary + per-student rollup. */
export function useAttendanceReport(params: ReportParams | null) {
  return useQuery({
    queryKey: ["attendance-report", params],
    enabled: params !== null,
    queryFn: () =>
      apiGet<AttendanceReport>("/schools/attendance/report", {
        params: {
          from: params!.from,
          to: params!.to,
          class_grade: params!.class_grade || undefined,
        },
      }),
  });
}

/** Distinct class/grade values from the roster, for the filter dropdown. */
export function useClassGrades() {
  return useQuery({
    queryKey: ["class-grades"],
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const { items } = await apiGetList<RosterRow[]>("/schools/students", {
        params: { limit: 500 },
      });
      const grades = new Set<string>();
      for (const row of items) {
        if (row.class_grade) grades.add(row.class_grade);
      }
      return Array.from(grades).sort();
    },
  });
}

/**
 * GET /schools/attendance/export — fetch the CSV as a blob (bearer-authed) and
 * trigger a browser download. Filename comes from Content-Disposition when present.
 */
export async function downloadAttendanceCsv(params: ReportParams): Promise<void> {
  const resp = await api.get("/schools/attendance/export", {
    params: {
      from: params.from,
      to: params.to,
      class_grade: params.class_grade || undefined,
    },
    responseType: "blob",
  });

  const filename =
    parseFilename(resp.headers["content-disposition"]) ??
    `attendance_${params.from}_${params.to}.csv`;

  const url = URL.createObjectURL(resp.data as Blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function parseFilename(disposition: unknown): string | null {
  if (typeof disposition !== "string") return null;
  const match = /filename="?([^"]+)"?/.exec(disposition);
  return match ? match[1] : null;
}
