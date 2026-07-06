/** Daily register data hooks + manual-override mutation. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiGet, apiPut } from "@/lib/api";
import type { AttendanceStatus } from "./types";

export interface DailyRegisterRow {
  enrollment_id: string;
  child_id: string;
  child_name: string;
  class_grade: string | null;
  status: AttendanceStatus;
  arrival_time: string | null;
  departure_time: string | null;
}

export interface RegisterParams {
  date: string; // YYYY-MM-DD
  class_grade?: string;
}

/** GET /schools/attendance?date=&class_grade= — one row per consented student. */
export function useDailyRegister(params: RegisterParams | null) {
  return useQuery({
    queryKey: ["daily-register", params],
    enabled: params !== null,
    queryFn: () =>
      apiGet<DailyRegisterRow[]>("/schools/attendance", {
        params: {
          date: params!.date,
          class_grade: params!.class_grade || undefined,
        },
      }),
  });
}

export interface ManualOverride {
  enrollmentId: string;
  date: string;
  status: AttendanceStatus;
  /** Optional local (school-tz) arrival time-of-day, "HH:MM". */
  arrival_time?: string;
}

/** PUT /schools/students/{enrollment_id}/attendance — manual override. */
export function useSetManualAttendance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ enrollmentId, date, status, arrival_time }: ManualOverride) =>
      apiPut(`/schools/students/${enrollmentId}/attendance`, {
        date,
        status,
        arrival_time: arrival_time || null,
      }),
    onSuccess: () => {
      toast.success("Attendance updated");
      qc.invalidateQueries({ queryKey: ["daily-register"] });
    },
  });
}
