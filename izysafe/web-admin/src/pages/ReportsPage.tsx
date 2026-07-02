import { PlaceholderPage } from "@/components/PlaceholderPage";

export function ReportsPage() {
  return (
    <PlaceholderPage
      title="Reports"
      description="Date-range attendance summary and per-student rollup, with CSV export."
      planned="Coming next: report view (GET /schools/attendance/report) + CSV download (GET /schools/attendance/export)."
    />
  );
}
