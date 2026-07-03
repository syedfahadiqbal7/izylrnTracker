import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

export interface DashboardStats {
  buses_total: number;
  buses_online: number;
  students_enrolled: number;
  consented: number;
  pending_consents: number;
  location_consented: number;
  students_present: number;
  active_trips: number;
}

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => apiGet<DashboardStats>("/schools/dashboard/stats"),
    refetchInterval: 30_000,
  });
}
