import { useEffect, useMemo, useState } from "react";
import type { DateRange } from "react-day-picker";
import { endOfDay, format, startOfDay } from "date-fns";
import { Download, Loader2, ShieldAlert } from "lucide-react";
import { useAuth } from "@/auth/useAuth";
import { useT } from "@/lib/i18n/I18nProvider";
import { PageHeader } from "@/components/PageHeader";
import { DateRangePicker } from "@/components/DateRangePicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
  actionLabel,
  actorLabel,
  downloadAuditCsv,
  entityLabel,
  ENTITY_TYPES,
  FILTERABLE_ACTIONS,
  useAudit,
  type AuditEntry,
  type AuditFilters,
} from "@/features/audit/api";

const ALL = "__all__";
const PAGE_SIZE = 25;

const actorVariant = (t: string): "secondary" | "muted" =>
  t === "school_admin" ? "secondary" : "muted";

function renderDetails(details: Record<string, unknown> | null) {
  if (!details || Object.keys(details).length === 0) return "—";
  return Object.entries(details)
    .map(([k, v]) => `${k}: ${v ?? "—"}`)
    .join(" · ");
}

export function AuditPage() {
  const { admin } = useAuth();
  const t = useT();
  const [range, setRange] = useState<DateRange | undefined>();
  const [actor, setActor] = useState<string>(ALL);
  const [action, setAction] = useState<string>(ALL);
  const [entity, setEntity] = useState<string>(ALL);
  const [page, setPage] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => setPage(0), [range, actor, action, entity]);

  const filters: AuditFilters = useMemo(
    () => ({
      from: range?.from ? startOfDay(range.from).toISOString() : undefined,
      to: range?.to ? endOfDay(range.to).toISOString() : undefined,
      actor_type: actor === ALL ? undefined : actor,
      action: action === ALL ? undefined : action,
      entity_type: entity === ALL ? undefined : entity,
    }),
    [range, actor, action, entity],
  );

  // Admins only — the backend enforces this too (403 for staff).
  if (admin?.role !== "admin") {
    return (
      <>
        <PageHeader title={t("audit.title", "Audit Log")} description={t("audit.trail", "The school's activity trail.")} />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldAlert className="size-9 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              {t("audit.admin_only", "The audit log is available to administrators only.")}
            </p>
          </CardContent>
        </Card>
      </>
    );
  }

  return <AuditContent filters={filters}
    range={range} setRange={setRange}
    actor={actor} setActor={setActor}
    action={action} setAction={setAction}
    entity={entity} setEntity={setEntity}
    page={page} setPage={setPage}
    exporting={exporting} setExporting={setExporting}
    exportError={exportError} setExportError={setExportError}
  />;
}

interface ContentProps {
  filters: AuditFilters;
  range: DateRange | undefined;
  setRange: (r: DateRange | undefined) => void;
  actor: string;
  setActor: (v: string) => void;
  action: string;
  setAction: (v: string) => void;
  entity: string;
  setEntity: (v: string) => void;
  page: number;
  setPage: (fn: (p: number) => number) => void;
  exporting: boolean;
  setExporting: (v: boolean) => void;
  exportError: string | null;
  setExportError: (v: string | null) => void;
}

function AuditContent(p: ContentProps) {
  const t = useT();
  const params = { ...p.filters, limit: PAGE_SIZE, offset: p.page * PAGE_SIZE };
  const audit = useAudit(params);

  const rows = audit.data?.items ?? [];
  const total = audit.data?.meta?.total ?? 0;
  const from = total === 0 ? 0 : p.page * PAGE_SIZE + 1;
  const to = Math.min(total, (p.page + 1) * PAGE_SIZE);

  const onExport = async () => {
    p.setExporting(true);
    p.setExportError(null);
    try {
      await downloadAuditCsv(p.filters);
    } catch (err) {
      p.setExportError(
        err instanceof ApiClientError ? err.message : t("audit.export_error", "Could not export the log."),
      );
    } finally {
      p.setExporting(false);
    }
  };

  return (
    <>
      <PageHeader
        title={t("audit.title", "Audit Log")}
        description={t("audit.desc", "Every recorded action in your school, newest first.")}
        actions={
          <Button onClick={onExport} disabled={p.exporting}>
            {p.exporting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4" />
            )}
            {t("audit.export", "Export CSV")}
          </Button>
        }
      />

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="flex flex-wrap items-end gap-4 pt-6">
          <div className="space-y-2">
            <Label>{t("common.date_range", "Date range")}</Label>
            <DateRangePicker value={p.range} onChange={p.setRange} />
          </div>
          <FilterSelect
            label={t("audit.actor", "Actor")}
            value={p.actor}
            onChange={p.setActor}
            allLabel={t("common.all", "All")}
            options={[
              { value: "school_admin", label: t("audit.admin", "Admin") },
              { value: "driver", label: t("nav.drivers", "Driver") },
              { value: "parent", label: t("audit.parent", "Parent") },
            ]}
          />
          <FilterSelect
            label={t("audit.action", "Action")}
            value={p.action}
            onChange={p.setAction}
            width="w-56"
            allLabel={t("common.all", "All")}
            options={FILTERABLE_ACTIONS.map((a) => ({
              value: a,
              label: actionLabel(a),
            }))}
          />
          <FilterSelect
            label={t("audit.entity", "Entity")}
            value={p.entity}
            onChange={p.setEntity}
            allLabel={t("common.all", "All")}
            options={ENTITY_TYPES.map((e) => ({ value: e, label: entityLabel(e) }))}
          />
        </CardContent>
      </Card>

      {p.exportError && (
        <p className="mb-4 text-sm font-medium text-destructive">{p.exportError}</p>
      )}

      {audit.isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm font-medium text-destructive">
            {audit.error instanceof ApiClientError
              ? audit.error.message
              : t("audit.load_error", "Failed to load the audit log.")}
          </CardContent>
        </Card>
      )}

      {audit.isLoading && (
        <Card>
          <CardContent className="space-y-3 pt-6">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </CardContent>
        </Card>
      )}

      {audit.isSuccess && (
        <Card>
          <CardContent className="pt-6">
            {rows.length === 0 ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                {t("audit.no_results", "No audit entries match these filters.")}
              </p>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-44">{t("audit.when", "When")}</TableHead>
                      <TableHead>{t("audit.actor", "Actor")}</TableHead>
                      <TableHead>{t("audit.action", "Action")}</TableHead>
                      <TableHead>{t("audit.entity", "Entity")}</TableHead>
                      <TableHead>{t("audit.details", "Details")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((r) => (
                      <AuditRow key={r.id} entry={r} />
                    ))}
                  </TableBody>
                </Table>

                <div className="mt-4 flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">
                    {from}–{to} {t("common.of", "of")} {total}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={p.page === 0 || audit.isFetching}
                      onClick={() => p.setPage((n) => Math.max(0, n - 1))}
                    >
                      {t("common.previous", "Previous")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={to >= total || audit.isFetching}
                      onClick={() => p.setPage((n) => n + 1)}
                    >
                      {t("common.next", "Next")}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  return (
    <TableRow>
      <TableCell className="tabular-nums text-muted-foreground">
        {format(new Date(entry.created_at), "d MMM yyyy, HH:mm")}
      </TableCell>
      <TableCell>
        <Badge variant={actorVariant(entry.actor_type)}>
          {actorLabel(entry.actor_type)}
        </Badge>
      </TableCell>
      <TableCell className="font-medium">{actionLabel(entry.action)}</TableCell>
      <TableCell className="text-muted-foreground">
        {entityLabel(entry.entity_type)}
      </TableCell>
      <TableCell className="max-w-sm truncate text-xs text-muted-foreground">
        {renderDetails(entry.details)}
      </TableCell>
    </TableRow>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel = "All",
  width = "w-40",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  allLabel?: string;
  width?: string;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className={width}>
          <SelectValue placeholder={allLabel} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>{allLabel}</SelectItem>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
