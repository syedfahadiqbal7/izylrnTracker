import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Bus,
  Check,
  Clock,
  Loader2,
  MapPin,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Trash2,
  UserPlus,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { useT } from "@/lib/i18n/I18nProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
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
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { ApiClientError } from "@/types/api";
import { useClassGrades } from "@/features/attendance/api";
import {
  useEnrollStudent,
  useRemoveEnrollment,
  useRoster,
  useUpdateEnrollment,
  type Enrollment,
} from "@/features/roster/api";

const ALL = "__all__";
const PAGE_SIZE = 20;

type ConsentFilter = "all" | "consented" | "pending";

export function RosterPage() {
  const t = useT();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search.trim(), 300);
  const [classGrade, setClassGrade] = useState<string>(ALL);
  const [consent, setConsent] = useState<ConsentFilter>("all");
  const [page, setPage] = useState(0);

  const [addOpen, setAddOpen] = useState(false);
  const [editFor, setEditFor] = useState<Enrollment | null>(null);
  const [removeFor, setRemoveFor] = useState<Enrollment | null>(null);

  // Any filter change resets to the first page.
  useEffect(() => setPage(0), [q, classGrade, consent]);

  const params = useMemo(
    () => ({
      q: q || undefined,
      class_grade: classGrade === ALL ? undefined : classGrade,
      opted_in:
        consent === "all" ? undefined : consent === "consented" ? true : false,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [q, classGrade, consent, page],
  );

  const roster = useRoster(params);
  const grades = useClassGrades();

  const rows = roster.data?.items ?? [];
  const total = roster.data?.meta?.total ?? 0;
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = Math.min(total, (page + 1) * PAGE_SIZE);

  return (
    <>
      <PageHeader
        title={t("roster.title", "Roster")}
        description={t("roster.desc", "Enrolled students, parent contacts, and consent status. Assign students to bus stops under Routes & Buses.")}
        actions={
          <Button onClick={() => setAddOpen(true)}>
            <Plus className="size-4" />
            {t("roster.add_student", "Add student")}
          </Button>
        }
      />

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="flex flex-wrap items-end gap-4 pt-6">
          <div className="space-y-2">
            <Label>{t("common.search", "Search")}</Label>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("roster.search_name", "Student name…")}
                className="w-64 pl-8"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>{t("att.class_grade", "Class / grade")}</Label>
            <Select value={classGrade} onValueChange={setClassGrade}>
              <SelectTrigger className="w-44">
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
          <div className="space-y-2">
            <Label>{t("roster.consent", "Consent")}</Label>
            <Select
              value={consent}
              onValueChange={(v) => setConsent(v as ConsentFilter)}
            >
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("common.all", "All")}</SelectItem>
                <SelectItem value="consented">{t("roster.consented", "Consented")}</SelectItem>
                <SelectItem value="pending">{t("roster.pending", "Pending")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {roster.isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm font-medium text-destructive">
            {roster.error instanceof ApiClientError
              ? roster.error.message
              : t("roster.load_error", "Failed to load the roster.")}
          </CardContent>
        </Card>
      )}

      {roster.isLoading && (
        <Card>
          <CardContent className="space-y-3 pt-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </CardContent>
        </Card>
      )}

      {roster.isSuccess && (
        <Card>
          <CardContent className="pt-6">
            {rows.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-14 text-center">
                <UserPlus className="size-9 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  {q || classGrade !== ALL || consent !== "all"
                    ? t("roster.no_match", "No students match these filters.")
                    : t("roster.empty", "No students enrolled yet.")}
                </p>
              </div>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("common.student", "Student")}</TableHead>
                      <TableHead>{t("common.class", "Class")}</TableHead>
                      <TableHead>{t("roster.parent", "Parent")}</TableHead>
                      <TableHead>{t("roster.contact", "Contact")}</TableHead>
                      <TableHead>{t("roster.bus", "Bus")}</TableHead>
                      <TableHead>{t("roster.consent", "Consent")}</TableHead>
                      <TableHead className="text-right">{t("common.actions", "Actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="font-medium">
                          {r.child_name}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {r.class_grade ?? "—"}
                        </TableCell>
                        <TableCell>{r.parent_name ?? "—"}</TableCell>
                        <TableCell className="tabular-nums text-muted-foreground">
                          {r.parent_phone ?? "—"}
                        </TableCell>
                        <TableCell>
                          {r.bus_opt_in ? (
                            <Badge variant="secondary" className="gap-1">
                              <Bus className="size-3" />
                              {t("roster.yes", "Yes")}
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap items-center gap-1.5">
                            {r.parent_opt_in ? (
                              <Badge variant="success" className="gap-1">
                                <Check className="size-3" />
                                {t("roster.consented", "Consented")}
                              </Badge>
                            ) : (
                              <Badge variant="warning" className="gap-1">
                                <Clock className="size-3" />
                                {t("roster.pending", "Pending")}
                              </Badge>
                            )}
                            {r.location_opt_in && (
                              <Badge variant="secondary" className="gap-1">
                                <MapPin className="size-3" />
                                {t("roster.location", "Location")}
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon">
                                <MoreHorizontal className="size-4" />
                                <span className="sr-only">{t("roster.open_actions", "Open actions")}</span>
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setEditFor(r)}>
                                <Pencil className="size-4" />
                                {t("roster.edit_class", "Edit class / grade")}
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={() => setRemoveFor(r)}
                              >
                                <Trash2 className="size-4" />
                                {t("roster.remove_from_roster", "Remove from roster")}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                <div className="mt-4 flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">
                    {from}–{to} {t("roster.of", "of")} {total}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page === 0 || roster.isFetching}
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                    >
                      {t("roster.previous", "Previous")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={to >= total || roster.isFetching}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      {t("roster.next", "Next")}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <AddStudentDialog open={addOpen} onClose={() => setAddOpen(false)} />
      <EditClassDialog enrollment={editFor} onClose={() => setEditFor(null)} />
      <RemoveStudentDialog
        enrollment={removeFor}
        onClose={() => setRemoveFor(null)}
      />
    </>
  );
}

function AddStudentDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const enroll = useEnrollStudent();
  const [phone, setPhone] = useState("");
  const [childName, setChildName] = useState("");
  const [classGrade, setClassGrade] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [wasOpen, setWasOpen] = useState(false);
  if (open && !wasOpen) {
    setWasOpen(true);
    setPhone("");
    setChildName("");
    setClassGrade("");
    setError(null);
    enroll.reset();
  }
  if (!open && wasOpen) setWasOpen(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await enroll.mutateAsync({
        phone: phone.trim(),
        child_name: childName.trim() || undefined,
        class_grade: classGrade.trim() || undefined,
      });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("roster.enroll_error", "Could not enroll the student."),
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{t("roster.add_student", "Add student")}</DialogTitle>
            <DialogDescription>
              {t("roster.add_desc_pre", "Enroll a student by their parent's phone number. The parent must already use the IzySafe app, and approves visibility from their side — the enrollment starts as")}{" "}
              <b>{t("roster.pending", "Pending")}</b>{" "}
              {t("roster.add_desc_post", "consent.")}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="s-phone">{t("roster.parent_phone", "Parent phone")}</Label>
              <Input
                id="s-phone"
                required
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91…"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="s-child">
                {t("roster.student_name", "Student name")}{" "}
                <span className="font-normal text-muted-foreground">
                  ({t("roster.student_name_hint", "required if the parent has more than one child")})
                </span>
              </Label>
              <Input
                id="s-child"
                value={childName}
                onChange={(e) => setChildName(e.target.value)}
                placeholder={t("roster.eg_aarav", "e.g. Aarav")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="s-class">
                {t("att.class_grade", "Class / grade")}{" "}
                <span className="font-normal text-muted-foreground">
                  ({t("roster.optional", "optional")})
                </span>
              </Label>
              <Input
                id="s-class"
                value={classGrade}
                onChange={(e) => setClassGrade(e.target.value)}
                placeholder={t("roster.eg_5a", "e.g. 5A")}
              />
            </div>
            {error && (
              <p className="text-sm font-medium text-destructive">{error}</p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={enroll.isPending}
            >
              {t("common.cancel", "Cancel")}
            </Button>
            <Button type="submit" disabled={enroll.isPending || !phone.trim()}>
              {enroll.isPending && <Loader2 className="size-4 animate-spin" />}
              {t("roster.add_student", "Add student")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EditClassDialog({
  enrollment,
  onClose,
}: {
  enrollment: Enrollment | null;
  onClose: () => void;
}) {
  const t = useT();
  const update = useUpdateEnrollment();
  const [classGrade, setClassGrade] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [seededFor, setSeededFor] = useState<string | null>(null);
  if (enrollment && seededFor !== enrollment.id) {
    setSeededFor(enrollment.id);
    setClassGrade(enrollment.class_grade ?? "");
    setError(null);
    update.reset();
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!enrollment) return;
    setError(null);
    try {
      await update.mutateAsync({
        id: enrollment.id,
        class_grade: classGrade.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("roster.save_change_error", "Could not save the change."),
      );
    }
  };

  return (
    <Dialog open={enrollment !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{t("roster.edit_class", "Edit class / grade")}</DialogTitle>
            <DialogDescription>
              {enrollment?.child_name} {t("roster.edit_class_desc", "— the student's name and profile are managed by their parent.")}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 py-4">
            <Label htmlFor="e-class">{t("att.class_grade", "Class / grade")}</Label>
            <Input
              id="e-class"
              autoFocus
              value={classGrade}
              onChange={(e) => setClassGrade(e.target.value)}
              placeholder={t("roster.eg_6b", "e.g. 6B")}
            />
            {error && (
              <p className="text-sm font-medium text-destructive">{error}</p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={update.isPending}
            >
              {t("common.cancel", "Cancel")}
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending && <Loader2 className="size-4 animate-spin" />}
              {t("common.save", "Save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RemoveStudentDialog({
  enrollment,
  onClose,
}: {
  enrollment: Enrollment | null;
  onClose: () => void;
}) {
  const t = useT();
  const remove = useRemoveEnrollment();
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    if (!enrollment) return;
    setError(null);
    try {
      await remove.mutateAsync(enrollment.id);
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("roster.remove_error", "Could not remove the student."),
      );
    }
  };

  return (
    <Dialog open={enrollment !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("roster.remove_student", "Remove student")}</DialogTitle>
          <DialogDescription>
            {t("roster.remove_desc_pre", "Remove")}{" "}
            <span className="font-medium">{enrollment?.child_name}</span>{" "}
            {t("roster.remove_desc_post", "from the roster? Their attendance history is retained, but the school will no longer see this student.")}
          </DialogDescription>
        </DialogHeader>
        {error && (
          <p className="text-sm font-medium text-destructive">{error}</p>
        )}
        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={remove.isPending}
          >
            {t("common.cancel", "Cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={confirm}
            disabled={remove.isPending}
          >
            {remove.isPending && <Loader2 className="size-4 animate-spin" />}
            {t("roster.remove", "Remove")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
