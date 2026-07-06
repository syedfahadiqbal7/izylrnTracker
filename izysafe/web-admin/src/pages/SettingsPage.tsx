import { useEffect, useState, type FormEvent } from "react";
import { format } from "date-fns";
import { Loader2, MoreHorizontal, Plus, UserCog, X } from "lucide-react";
import { useAuth } from "@/auth/useAuth";
import { PageHeader } from "@/components/PageHeader";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { ApiClientError } from "@/types/api";
import { useT } from "@/lib/i18n/I18nProvider";
import { LocalizationCard } from "@/features/localization/LocalizationCard";
import { useSchool, type School } from "@/features/school/api";
import {
  useAdmins,
  useChangePassword,
  useDeleteAdmin,
  useInviteStaff,
  useManageAdmin,
  useSetAdminActive,
  useUpdateMyName,
  useUpdateSchool,
  type AdminRole,
  type SchoolAdminRow,
} from "@/features/settings/api";

const TIMEZONES = [
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Karachi",
  "Asia/Dhaka",
  "Asia/Kathmandu",
  "UTC",
];
const hhmm = (t: string | null | undefined) => (t ? t.slice(0, 5) : "");

export function SettingsPage() {
  const { admin } = useAuth();
  const t = useT();
  const school = useSchool();
  const isAdmin = admin?.role === "admin";

  return (
    <>
      <PageHeader
        title={t("settings.title", "Settings")}
        description={t("settings.desc", "School profile, attendance configuration, localization, your account, and staff.")}
      />
      {school.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : school.isSuccess ? (
        <div className="space-y-6">
          <SchoolProfileCard school={school.data} canEdit={isAdmin} />
          <AttendanceConfigCard school={school.data} canEdit={isAdmin} />
          <MyAccountCard />
          <AdminsCard isAdmin={isAdmin} meId={admin?.id} />
          {isAdmin && <LocalizationCard />}
        </div>
      ) : (
        <Card>
          <CardContent className="py-12 text-center text-sm font-medium text-destructive">
            {t("settings.load_error", "Failed to load settings.")}
          </CardContent>
        </Card>
      )}
    </>
  );
}

function SavedHint({ show }: { show: boolean }) {
  const t = useT();
  if (!show) return null;
  return <span className="text-sm font-medium text-emerald-600">{t("settings.saved", "Saved ✓")}</span>;
}

// --------------------------------------------------------------------------- //
// School profile
// --------------------------------------------------------------------------- //
function SchoolProfileCard({ school, canEdit }: { school: School; canEdit: boolean }) {
  const t = useT();
  const update = useUpdateSchool();
  const [name, setName] = useState(school.name);
  const [address, setAddress] = useState(school.address ?? "");
  const [phone, setPhone] = useState(school.contact_phone ?? "");
  const [email, setEmail] = useState(school.contact_email ?? "");
  const [timezone, setTimezone] = useState(school.timezone);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const tzOptions = TIMEZONES.includes(school.timezone)
    ? TIMEZONES
    : [school.timezone, ...TIMEZONES];

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaved(false);
    try {
      await update.mutateAsync({
        name: name.trim(),
        address: address.trim() || null,
        contact_phone: phone.trim() || null,
        contact_email: email.trim() || null,
        timezone,
      });
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : t("settings.could_not_save", "Could not save."));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.school_profile", "School profile")}</CardTitle>
        <CardDescription>{t("settings.school_profile_desc", "Name, address, and contact details.")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="sc-name">{t("settings.school_name", "School name")}</Label>
              <Input
                id="sc-name"
                value={name}
                disabled={!canEdit}
                onChange={(e) => {
                  setName(e.target.value);
                  setSaved(false);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label>{t("settings.timezone", "Timezone")}</Label>
              <Select
                value={timezone}
                onValueChange={(v) => {
                  setTimezone(v);
                  setSaved(false);
                }}
                disabled={!canEdit}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {tzOptions.map((tz) => (
                    <SelectItem key={tz} value={tz}>
                      {tz}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="sc-addr">{t("settings.address", "Address")}</Label>
            <Input
              id="sc-addr"
              value={address}
              disabled={!canEdit}
              onChange={(e) => {
                setAddress(e.target.value);
                setSaved(false);
              }}
              placeholder={t("settings.address_ph", "Street, city")}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="sc-phone">{t("settings.contact_phone", "Contact phone")}</Label>
              <Input
                id="sc-phone"
                value={phone}
                disabled={!canEdit}
                onChange={(e) => {
                  setPhone(e.target.value);
                  setSaved(false);
                }}
                placeholder="+91…"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sc-email">{t("settings.contact_email", "Contact email")}</Label>
              <Input
                id="sc-email"
                type="email"
                value={email}
                disabled={!canEdit}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setSaved(false);
                }}
                placeholder="office@school.edu"
              />
            </div>
          </div>
          {error && <p className="text-sm font-medium text-destructive">{error}</p>}
          {canEdit ? (
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={update.isPending || !name.trim()}>
                {update.isPending && <Loader2 className="size-4 animate-spin" />}
                {t("settings.save_profile", "Save profile")}
              </Button>
              <SavedHint show={saved} />
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              {t("settings.admin_edit_only", "Only administrators can edit school settings.")}
            </p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------- //
// Attendance & calendar
// --------------------------------------------------------------------------- //
function AttendanceConfigCard({ school, canEdit }: { school: School; canEdit: boolean }) {
  const t = useT();
  const update = useUpdateSchool();
  const [onTime, setOnTime] = useState(hhmm(school.on_time_before));
  const [lateUntil, setLateUntil] = useState(hhmm(school.late_until));
  const [windowFrom, setWindowFrom] = useState(hhmm(school.arrival_window_from));
  const [dayEnds, setDayEnds] = useState(hhmm(school.day_ends_at));
  const [holidays, setHolidays] = useState<string[]>(school.holidays ?? []);
  const [newHoliday, setNewHoliday] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const addHoliday = () => {
    if (newHoliday && !holidays.includes(newHoliday)) {
      setHolidays([...holidays, newHoliday].sort());
      setNewHoliday("");
      setSaved(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaved(false);
    try {
      await update.mutateAsync({
        on_time_before: onTime,
        late_until: lateUntil,
        arrival_window_from: windowFrom,
        day_ends_at: dayEnds,
        holidays,
      });
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : t("settings.could_not_save", "Could not save."));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.attendance_calendar", "Attendance & calendar")}</CardTitle>
        <CardDescription>
          {t("settings.attendance_calendar_desc", "Arrival window, on-time / late thresholds, and holidays.")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="cf-window">{t("settings.arrival_window", "Arrival window opens")}</Label>
              <Input
                id="cf-window"
                type="time"
                value={windowFrom}
                disabled={!canEdit}
                onChange={(e) => {
                  setWindowFrom(e.target.value);
                  setSaved(false);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cf-ontime">{t("settings.on_time_before", "On-time before")}</Label>
              <Input
                id="cf-ontime"
                type="time"
                value={onTime}
                disabled={!canEdit}
                onChange={(e) => {
                  setOnTime(e.target.value);
                  setSaved(false);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cf-late">{t("settings.late_until", "Late until")}</Label>
              <Input
                id="cf-late"
                type="time"
                value={lateUntil}
                disabled={!canEdit}
                onChange={(e) => {
                  setLateUntil(e.target.value);
                  setSaved(false);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cf-end">{t("settings.day_ends", "School day ends")}</Label>
              <Input
                id="cf-end"
                type="time"
                value={dayEnds}
                disabled={!canEdit}
                onChange={(e) => {
                  setDayEnds(e.target.value);
                  setSaved(false);
                }}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {t("settings.location_visibility_note", "Students' live location is visible to the school only between the arrival window and the end of the school day, on school days.")}
          </p>

          <div className="space-y-2">
            <Label>{t("settings.holidays", "Holidays")}</Label>
            <div className="flex flex-wrap gap-2">
              {holidays.length === 0 && (
                <span className="text-sm text-muted-foreground">
                  {t("settings.no_holidays", "No holidays set.")}
                </span>
              )}
              {holidays.map((h) => (
                <Badge key={h} variant="secondary" className="gap-1 py-1">
                  {h}
                  {canEdit && (
                    <button
                      type="button"
                      onClick={() => {
                        setHolidays(holidays.filter((x) => x !== h));
                        setSaved(false);
                      }}
                      className="ml-0.5 rounded-full hover:text-destructive"
                    >
                      <X className="size-3" />
                    </button>
                  )}
                </Badge>
              ))}
            </div>
            {canEdit && (
              <div className="flex gap-2 pt-1">
                <Input
                  type="date"
                  value={newHoliday}
                  onChange={(e) => setNewHoliday(e.target.value)}
                  className="w-48"
                />
                <Button type="button" variant="outline" onClick={addHoliday}>
                  {t("settings.add_holiday", "Add holiday")}
                </Button>
              </div>
            )}
          </div>

          {error && <p className="text-sm font-medium text-destructive">{error}</p>}
          {canEdit ? (
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={update.isPending}>
                {update.isPending && <Loader2 className="size-4 animate-spin" />}
                {t("settings.save_configuration", "Save configuration")}
              </Button>
              <SavedHint show={saved} />
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              {t("settings.admin_edit_only", "Only administrators can edit school settings.")}
            </p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------- //
// My account
// --------------------------------------------------------------------------- //
function MyAccountCard() {
  const t = useT();
  const { admin, refreshAdmin } = useAuth();
  const updateName = useUpdateMyName();
  const [name, setName] = useState(admin?.name ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);

  useEffect(() => {
    setName(admin?.name ?? "");
  }, [admin?.name]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaved(false);
    try {
      await updateName.mutateAsync(name.trim());
      await refreshAdmin();
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : t("settings.could_not_save", "Could not save."));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.my_account", "My account")}</CardTitle>
        <CardDescription>{t("settings.my_account_desc", "Your profile and password.")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="me-email">{t("common.email", "Email")}</Label>
              <Input id="me-email" value={admin?.email ?? ""} disabled />
            </div>
            <div className="space-y-2">
              <Label htmlFor="me-name">{t("common.name", "Name")}</Label>
              <Input
                id="me-name"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setSaved(false);
                }}
                placeholder={t("settings.your_name", "Your name")}
              />
            </div>
          </div>
          {error && <p className="text-sm font-medium text-destructive">{error}</p>}
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={updateName.isPending}>
              {updateName.isPending && <Loader2 className="size-4 animate-spin" />}
              {t("common.save", "Save")}
            </Button>
            <Button type="button" variant="outline" onClick={() => setPwOpen(true)}>
              {t("settings.change_password", "Change password")}
            </Button>
            <SavedHint show={saved} />
          </div>
        </form>
      </CardContent>
      {pwOpen && <ChangePasswordDialog onClose={() => setPwOpen(false)} />}
    </Card>
  );
}

function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const t = useT();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next.length < 8) {
      setError(t("settings.pw_min", "New password must be at least 8 characters."));
      return;
    }
    try {
      await change.mutateAsync({ current_password: current, new_password: next });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError ? err.message : t("settings.pw_change_error", "Could not change password."),
      );
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{t("settings.change_password", "Change password")}</DialogTitle>
            <DialogDescription>
              {t("settings.change_password_desc", "Enter your current password and choose a new one (min 8 characters).")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="pw-cur">{t("settings.current_password", "Current password")}</Label>
              <Input
                id="pw-cur"
                type="password"
                autoComplete="current-password"
                required
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="pw-new">{t("settings.new_password", "New password")}</Label>
              <Input
                id="pw-new"
                type="password"
                autoComplete="new-password"
                required
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
            </div>
            {error && (
              <p className="text-sm font-medium text-destructive">{error}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={change.isPending}>
              {t("common.cancel", "Cancel")}
            </Button>
            <Button type="submit" disabled={change.isPending}>
              {change.isPending && <Loader2 className="size-4 animate-spin" />}
              {t("settings.update_password", "Update password")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------- //
// Admins & staff
// --------------------------------------------------------------------------- //
function AdminsCard({ isAdmin, meId }: { isAdmin: boolean; meId?: string }) {
  const t = useT();
  const admins = useAdmins();
  const setActive = useSetAdminActive();
  const manage = useManageAdmin();
  const del = useDeleteAdmin();
  const [addOpen, setAddOpen] = useState(false);
  const [deleteFor, setDeleteFor] = useState<SchoolAdminRow | null>(null);

  const rows = admins.data ?? [];

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <UserCog className="size-5" />
            {t("settings.admins_staff", "Admins & staff")}
          </CardTitle>
          <CardDescription>
            {t("settings.admins_staff_desc", "People who can access this school's panel.")}
          </CardDescription>
        </div>
        {isAdmin && (
          <Button size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="size-4" />
            {t("settings.add_staff", "Add staff")}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {admins.isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("common.name", "Name")}</TableHead>
                <TableHead>{t("common.email", "Email")}</TableHead>
                <TableHead>{t("settings.role", "Role")}</TableHead>
                <TableHead>{t("common.status", "Status")}</TableHead>
                <TableHead>{t("settings.last_login", "Last login")}</TableHead>
                {isAdmin && <TableHead className="text-right">{t("common.actions", "Actions")}</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium">
                    {a.name ?? "—"}
                    {a.id === meId && (
                      <Badge variant="secondary" className="ml-2 py-0 text-[10px]">
                        {t("settings.you", "You")}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{a.email}</TableCell>
                  <TableCell>
                    <Badge variant={a.role === "admin" ? "default" : "muted"}>
                      {a.role === "admin" ? t("settings.admin", "Admin") : t("settings.staff", "Staff")}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={a.active ? "success" : "muted"}>
                      {a.active ? t("settings.active", "Active") : t("settings.inactive", "Inactive")}
                    </Badge>
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {a.last_login_at
                      ? format(new Date(a.last_login_at), "d MMM yyyy, HH:mm")
                      : t("settings.never", "Never")}
                  </TableCell>
                  {isAdmin && (
                    <TableCell className="text-right">
                      {a.id !== meId ? (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() =>
                                manage.mutate({
                                  id: a.id,
                                  role: a.role === "admin" ? "staff" : "admin",
                                })
                              }
                            >
                              {a.role === "admin"
                                ? t("settings.make_staff", "Make staff")
                                : t("settings.make_admin", "Make admin")}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() =>
                                setActive.mutate({ id: a.id, active: !a.active })
                              }
                            >
                              {a.active
                                ? t("settings.deactivate", "Deactivate")
                                : t("settings.reactivate", "Reactivate")}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => setDeleteFor(a)}
                            >
                              {t("common.delete", "Delete")}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {addOpen && <AddStaffDialog onClose={() => setAddOpen(false)} />}
      <ConfirmDialog
        open={deleteFor !== null}
        onOpenChange={(o) => !o && setDeleteFor(null)}
        title={t("settings.delete_member", "Delete member")}
        description={
          <>
            {t("settings.delete_member_prefix", "Delete")}{" "}
            <span className="font-medium">{deleteFor?.email}</span>
            {t("settings.delete_member_suffix", "? They will lose access immediately.")}
          </>
        }
        confirmLabel={t("common.delete", "Delete")}
        destructive
        onConfirm={() => del.mutateAsync(deleteFor!.id).then(() => setDeleteFor(null))}
      />
    </Card>
  );
}

function AddStaffDialog({ onClose }: { onClose: () => void }) {
  const t = useT();
  const invite = useInviteStaff();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<AdminRole>("staff");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError(t("settings.password_min", "Password must be at least 8 characters."));
      return;
    }
    try {
      await invite.mutateAsync({
        email: email.trim(),
        password,
        name: name.trim() || undefined,
        role,
      });
      onClose();
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : t("settings.add_member_error", "Could not add member."));
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{t("settings.add_staff_admin", "Add staff / admin")}</DialogTitle>
            <DialogDescription>
              {t("settings.add_staff_desc", "Create an account for a colleague. Share the password with them securely — they can change it after signing in.")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="st-email">{t("common.email", "Email")}</Label>
              <Input
                id="st-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="colleague@school.edu"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="st-name">
                  {t("common.name", "Name")}{" "}
                  <span className="font-normal text-muted-foreground">
                    {t("settings.optional", "(optional)")}
                  </span>
                </Label>
                <Input
                  id="st-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>{t("settings.role", "Role")}</Label>
                <Select value={role} onValueChange={(v) => setRole(v as AdminRole)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="staff">{t("settings.staff", "Staff")}</SelectItem>
                    <SelectItem value="admin">{t("settings.admin", "Admin")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="st-pw">{t("settings.temp_password", "Temporary password (min 8)")}</Label>
              <Input
                id="st-pw"
                type="text"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t("settings.at_least_8", "At least 8 characters")}
              />
            </div>
            {error && <p className="text-sm font-medium text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={invite.isPending}>
              {t("common.cancel", "Cancel")}
            </Button>
            <Button
              type="submit"
              disabled={invite.isPending || !email.trim() || password.length < 8}
            >
              {invite.isPending && <Loader2 className="size-4 animate-spin" />}
              {t("settings.add_member", "Add member")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
