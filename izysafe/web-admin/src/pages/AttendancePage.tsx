import { useMemo, useState } from "react";
import { format } from "date-fns";
import { Loader2, PencilLine, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { useT } from "@/lib/i18n/I18nProvider";
import { DatePicker } from "@/components/DatePicker";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { useClassGrades } from "@/features/attendance/api";
import {
  useDailyRegister,
  useSetManualAttendance,
  type DailyRegisterRow,
  type RegisterParams,
} from "@/features/attendance/register";
import {
  OVERRIDE_STATUSES,
  STATUS_META,
  StatusBadge,
} from "@/features/attendance/status";
import type { AttendanceStatus } from "@/features/attendance/types";
import { useSchool } from "@/features/school/api";

const ALL = "__all__";
const fmtDate = (d: Date) => format(d, "yyyy-MM-dd");

function fmtTime(iso: string | null, tz: string | undefined) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: tz || undefined,
  }).format(new Date(iso));
}

export function AttendancePage() {
  const t = useT();
  const [date, setDate] = useState<Date>(() => new Date());
  const [classGrade, setClassGrade] = useState<string>(ALL);
  const [editRow, setEditRow] = useState<DailyRegisterRow | null>(null);

  const params: RegisterParams = useMemo(
    () => ({
      date: fmtDate(date),
      class_grade: classGrade === ALL ? undefined : classGrade,
    }),
    [date, classGrade],
  );

  const register = useDailyRegister(params);
  const grades = useClassGrades();
  const school = useSchool();
  const rows = register.data ?? [];

  const tally = useMemo(() => {
    const t: Record<string, number> = {};
    for (const r of rows) t[r.status] = (t[r.status] ?? 0) + 1;
    return t;
  }, [rows]);

  return (
    <>
      <PageHeader
        title={t("attendance.title", "Daily Attendance")}
        description={t("attendance.desc", "The register for a single day — every consented student's status.")}
        actions={
          <Button
            variant="outline"
            onClick={() => register.refetch()}
            disabled={register.isFetching}
          >
            <RefreshCw
              className={register.isFetching ? "size-4 animate-spin" : "size-4"}
            />
            {t("att.refresh", "Refresh")}
          </Button>
        }
      />

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="flex flex-wrap items-end gap-4 pt-6">
          <div className="space-y-2">
            <Label>{t("common.date", "Date")}</Label>
            <DatePicker value={date} onChange={(d) => d && setDate(d)} />
          </div>
          <div className="space-y-2">
            <Label>{t("att.class_grade", "Class / grade")}</Label>
            <Select value={classGrade} onValueChange={setClassGrade}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder={t("common.all_classes", "All classes")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t("common.all_classes", "All classes")}</SelectItem>
                {grades.data?.map((g) => (
                  <SelectItem key={g} value={g}>
                    {g}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {register.isSuccess && rows.length > 0 && (
            <div className="ml-auto flex flex-wrap gap-2 self-center">
              {OVERRIDE_STATUSES.concat("unknown" as AttendanceStatus).map(
                (s) =>
                  tally[s] ? (
                    <span
                      key={s}
                      className="flex items-center gap-1.5 text-sm text-muted-foreground"
                    >
                      <StatusBadge status={s} />
                      {tally[s]}
                    </span>
                  ) : null,
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {register.isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm font-medium text-destructive">
            {register.error instanceof ApiClientError
              ? register.error.message
              : t("att.load_error", "Failed to load the register.")}
          </CardContent>
        </Card>
      )}

      {register.isLoading && (
        <Card>
          <CardContent className="space-y-3 pt-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </CardContent>
        </Card>
      )}

      {register.isSuccess && (
        <Card>
          <CardContent className="pt-6">
            {rows.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                {t("att.no_consented", "No consented students")}{classGrade !== ALL ? t("att.in_this_class", " in this class") : ""}.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("common.student", "Student")}</TableHead>
                    <TableHead>{t("common.class", "Class")}</TableHead>
                    <TableHead>{t("common.status", "Status")}</TableHead>
                    <TableHead>{t("att.arrival", "Arrival")}</TableHead>
                    <TableHead>{t("att.departure", "Departure")}</TableHead>
                    <TableHead className="text-right">{t("common.action", "Action")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.enrollment_id}>
                      <TableCell className="font-medium">
                        {r.child_name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {r.class_grade ?? "—"}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={r.status} />
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {fmtTime(r.arrival_time, school.data?.timezone)}
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {fmtTime(r.departure_time, school.data?.timezone)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditRow(r)}
                        >
                          <PencilLine className="size-4" />
                          {t("att.override", "Override")}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      <OverrideDialog
        row={editRow}
        date={params.date}
        timezone={school.data?.timezone}
        onClose={() => setEditRow(null)}
      />
    </>
  );
}

function OverrideDialog({
  row,
  date,
  timezone,
  onClose,
}: {
  row: DailyRegisterRow | null;
  date: string;
  timezone: string | undefined;
  onClose: () => void;
}) {
  const t = useT();
  const mutation = useSetManualAttendance();
  const [status, setStatus] = useState<AttendanceStatus>("on_time");
  const [time, setTime] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  // Re-seed the form whenever a new row opens.
  const [seededFor, setSeededFor] = useState<string | null>(null);
  if (row && seededFor !== row.enrollment_id) {
    setSeededFor(row.enrollment_id);
    setStatus(
      OVERRIDE_STATUSES.includes(row.status) ? row.status : "on_time",
    );
    setTime("");
    setError(null);
    mutation.reset();
  }

  const submit = async () => {
    if (!row) return;
    setError(null);
    try {
      await mutation.mutateAsync({
        enrollmentId: row.enrollment_id,
        date,
        status,
        arrival_time: time || undefined,
      });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("att.save_error", "Could not save the override."),
      );
    }
  };

  const timeAllowed = status !== "absent";

  return (
    <Dialog open={row !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("att.override_title", "Override attendance")}</DialogTitle>
          <DialogDescription>
            {row?.child_name}
            {row?.class_grade ? ` · ${row.class_grade}` : ""} · {date}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t("common.status", "Status")}</Label>
            <Select
              value={status}
              onValueChange={(v) => setStatus(v as AttendanceStatus)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {OVERRIDE_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {STATUS_META[s].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>
              {t("att.arrival_time", "Arrival time")}{" "}
              <span className="font-normal text-muted-foreground">
                ({t("att.optional", "optional")}{timezone ? `, ${timezone}` : ""})
              </span>
            </Label>
            <Input
              type="time"
              value={time}
              disabled={!timeAllowed}
              onChange={(e) => setTime(e.target.value)}
            />
            {!timeAllowed && (
              <p className="text-xs text-muted-foreground">
                {t("att.absent_no_time", "Arrival time doesn't apply to an absent student.")}
              </p>
            )}
          </div>

          {error && (
            <p className="text-sm font-medium text-destructive">{error}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            {t("common.cancel", "Cancel")}
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending && (
              <Loader2 className="size-4 animate-spin" />
            )}
            {t("att.save_override", "Save override")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
