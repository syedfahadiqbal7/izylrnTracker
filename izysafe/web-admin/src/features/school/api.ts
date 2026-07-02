/** The caller's school profile (GET /schools/me) — used for timezone-aware display. */
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface School {
  id: string;
  name: string;
  timezone: string;
  holidays: string[] | null;
  on_time_before: string;
  late_until: string;
  arrival_window_from: string;
  created_at: string;
  updated_at: string;
}

export function useSchool() {
  return useQuery({
    queryKey: ["school-me"],
    staleTime: 5 * 60_000,
    queryFn: () => apiGet<School>("/schools/me"),
  });
}
