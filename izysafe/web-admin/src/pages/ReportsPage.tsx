import { useMemo, useState } from "react";
import type { DateRange } from "react-day-picker";
import { addDays, format } from "date-fns";
import { Download, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { useT } from "@/lib/i18n/I18nProvider";
import { DateRangePicker } from "@/components/DateRangePicker";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiClientError } from "@/types/api";
import {
  downloadAttendanceCsv,
  useAttendanceReport,
  useClassGrades,
} from "@/features/attendance/api";
import type {
  AttendanceStatus,
  ReportParams,
  StudentAttendanceSummary,
} from "@/features/attendance/types";

const ALL = "__all__";
const fmt = (d: Date) => format(d, "yyyy-MM-dd");
const pct = (rate: number) => `${(rate * 100).toFixed(1)}%`;

const STATUS_META: Record<
  AttendanceStatus,
  { label: string; variant: "success" | "warning" | "destructive" | "muted" }
> = {
  on_time: { label: "On time", variant: "success" },
  late: { label: "Late", variant: "warning" },
  early: { label: "Early", variant: "muted" },
  absent: { label: "Absent", variant: "destructive" },
  unknown: { label: "Unknown", variant: "muted" },
};
const STATUS_ORDER: AttendanceStatus[] = [
  "on_time",
  "late",
  "early",
  "absent",
  "unknown",
];

function rateVariant(rate: number): "success" | "warning" | "destructive" {
  if (rate >= 0.9) return "success";
  if (rate >= 0.75) return "warning";
  return "destructive";
}

export function ReportsPage() {
  const t = useT();
  const [range, setRange] = useState<DateRange | undefined>(() => {
    const today = new Date();
    return { from: addDays(today, -29), to: today };
  });
  const [classGrade, setClassGrade] = useState<string>(ALL);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const params: ReportParams | null = useMemo(() => {
    if (!range?.from || !range?.to) return null;
    return {
      from: fmt(range.from),
      to: fmt(range.to),
      class_grade: classGrade === ALL ? undefined : classGrade,
    };
  }, [range, classGrade]);

  const report = useAttendanceReport(params);
  const grades = useClassGrades();

  const onExport = async () => {
    if (!params) return;
    setExporting(true);
    setExportError(null);
    try {
      await downloadAttendanceCsv(params);
    } catch (err) {
      setExportError(
        err instanceof ApiClientError
          ? err.message
          : "Could not export the CSV. Please try again.",
      );
    } finally {
      setExporting(false);
    }
  };

  const summary = report.data?.summary;
  const rows = report.data?.per_student ?? [];

  return (
    <>
      <PageHeader
        title={t("reports.title", "Attendance Report")}
        description={t("reports.desc", "Date-range summary and per-student rollup across the attendance register.")}
        actions={
          <Button
            onClick={onExport}
            disabled={!params || exporting || report.isLoading}
          >
            {exporting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4" />
            )}
            Export CSV
          </Button>
        }
      />

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="flex flex-wrap items-end gap-4 pt-6">
          <div className="space-y-2">
            <Label>Date range</Label>
            <DateRangePicker value={range} onChange={setRange} />
          </div>
          <div className="space-y-2">
            <Label>Class / grade</Label>
            <Select value={classGrade} onValueChange={setClassGrade}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder={t("common.all_classes", "All classes")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All classes</SelectItem>
                {grades.data?.map((g) => (
                  <SelectItem key={g} value={g}>
                    {g}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {exportError && (
        <p className="mb-4 text-sm font-medium text-destructive">
          {exportError}
        </p>
      )}

      {!params && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Select a start and end date to generate the report.
          </CardContent>
        </Card>
      )}

      {params && report.isError && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm font-medium text-destructive">
              {report.error instanceof ApiClientError
                ? report.error.message
                : "Failed to load the report."}
            </p>
          </CardContent>
        </Card>
      )}

      {params && report.isLoading && <ReportSkeleton />}

      {params && report.isSuccess && summary && (
        <>
          {/* Summary cards */}
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Present rate"
              value={summary.records ? pct(summary.present_rate) : "—"}
              hint="On-time + late + early"
            />
            <StatCard label="Students" value={String(summary.students)} />
            <StatCard
              label="Total records"
              value={String(summary.records)}
              hint={`${report.data.date_from} → ${report.data.date_to}`}
            />
          </div>

          {/* By-status breakdown */}
          <Card className="mb-6">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">By status</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              {STATUS_ORDER.map((s) => (
                <div
                  key={s}
                  className="flex items-center gap-2 rounded-lg border px-3 py-2"
                >
                  <Badge variant={STATUS_META[s].variant}>
                    {STATUS_META[s].label}
                  </Badge>
                  <span className="text-sm font-semibold">
                    {summary.by_status[s] ?? 0}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {summary.records
                      ? pct((summary.by_status[s] ?? 0) / summary.records)
                      : "0.0%"}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Per-student table */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                Per-student ({rows.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {rows.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No attendance records in this range.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Student</TableHead>
                      <TableHead>Class</TableHead>
                      <TableHead className="text-right">On&nbsp;time</TableHead>
                      <TableHead className="text-right">Late</TableHead>
                      <TableHead className="text-right">Early</TableHead>
                      <TableHead className="text-right">Absent</TableHead>
                      <TableHead className="text-right">Unknown</TableHead>
                      <TableHead className="text-right">Present</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead className="text-right">Rate</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((r) => (
                      <StudentRow key={r.child_id} row={r} />
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </>
  );
}

function StudentRow({ row }: { row: StudentAttendanceSummary }) {
  return (
    <TableRow>
      <TableCell className="font-medium">{row.child_name}</TableCell>
      <TableCell className="text-muted-foreground">
        {row.class_grade ?? "—"}
      </TableCell>
      <TableCell className="text-right">{row.on_time}</TableCell>
      <TableCell className="text-right">{row.late}</TableCell>
      <TableCell className="text-right">{row.early}</TableCell>
      <TableCell className="text-right">{row.absent}</TableCell>
      <TableCell className="text-right">{row.unknown}</TableCell>
      <TableCell className="text-right font-medium">
        {row.present_days}
      </TableCell>
      <TableCell className="text-right">{row.total_days}</TableCell>
      <TableCell className="text-right">
        <Badge variant={rateVariant(row.rate)}>{pct(row.rate)}</Badge>
      </TableCell>
    </TableRow>
  );
}

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold tracking-tight">{value}</p>
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

function ReportSkeleton() {
  return (
    <>
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-9 w-20" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardContent className="space-y-3 pt-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </CardContent>
      </Card>
    </>
  );
}
