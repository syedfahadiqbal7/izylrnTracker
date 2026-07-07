import { useState, type FormEvent } from "react";
import { format } from "date-fns";
import {
  KeyRound,
  Loader2,
  MoreHorizontal,
  Plus,
  Power,
  ShieldAlert,
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
  randomAccessCode,
  useCreateDriver,
  useDeleteDriver,
  useDrivers,
  useSetActive,
  useSetDriverCode,
  type Driver,
} from "@/features/drivers/api";

function fmtLastLogin(t: ReturnType<typeof useT>, iso: string | null) {
  return iso ? format(new Date(iso), "d MMM yyyy, HH:mm") : t("drivers.never", "Never");
}

export function DriversPage() {
  const t = useT();
  const drivers = useDrivers();
  const setActive = useSetActive();
  const [addOpen, setAddOpen] = useState(false);
  const [codeFor, setCodeFor] = useState<Driver | null>(null);
  const [deleteFor, setDeleteFor] = useState<Driver | null>(null);

  const rows = drivers.data ?? [];

  return (
    <>
      <PageHeader
        title={t("drivers.title", "Drivers")}
        description={t("drivers.desc", "Bus drivers for your school, their access codes, and login activity.")}
        actions={
          <Button onClick={() => setAddOpen(true)}>
            <Plus className="size-4" />
            {t("drivers.add_driver", "Add driver")}
          </Button>
        }
      />

      {drivers.isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm font-medium text-destructive">
            {drivers.error instanceof ApiClientError
              ? drivers.error.message
              : t("drivers.load_failed", "Failed to load drivers.")}
          </CardContent>
        </Card>
      )}

      {drivers.isLoading && (
        <Card>
          <CardContent className="space-y-3 pt-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </CardContent>
        </Card>
      )}

      {drivers.isSuccess && (
        <Card>
          <CardContent className="pt-6">
            {rows.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-14 text-center">
                <UserPlus className="size-9 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  {t("drivers.empty", "No drivers yet. Add your first driver to get started.")}
                </p>
                <Button variant="outline" onClick={() => setAddOpen(true)}>
                  <Plus className="size-4" />
                  {t("drivers.add_driver", "Add driver")}
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("common.name", "Name")}</TableHead>
                    <TableHead>{t("common.phone", "Phone")}</TableHead>
                    <TableHead>{t("common.status", "Status")}</TableHead>
                    <TableHead>{t("common.last_login", "Last login")}</TableHead>
                    <TableHead className="text-right">{t("common.actions", "Actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((d) => (
                    <TableRow key={d.id}>
                      <TableCell className="font-medium">{d.name}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {d.phone ?? "—"}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge variant={d.active ? "success" : "muted"}>
                            {d.active ? t("common.active", "Active") : t("common.inactive", "Inactive")}
                          </Badge>
                          {!d.has_access_code && (
                            <Badge variant="warning" className="gap-1">
                              <ShieldAlert className="size-3" />
                              {t("drivers.no_code", "No code")}
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">
                        {fmtLastLogin(t, d.last_login_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="size-4" />
                              <span className="sr-only">{t("drivers.open_actions", "Open actions")}</span>
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => setCodeFor(d)}>
                              <KeyRound className="size-4" />
                              {d.has_access_code
                                ? t("drivers.reset_access_code", "Reset access code")
                                : t("drivers.set_access_code", "Set access code")}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              disabled={setActive.isPending}
                              onClick={() =>
                                setActive.mutate({ id: d.id, active: !d.active })
                              }
                            >
                              <Power className="size-4" />
                              {d.active ? t("drivers.deactivate", "Deactivate") : t("drivers.reactivate", "Reactivate")}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => setDeleteFor(d)}
                            >
                              <Trash2 className="size-4" />
                              {t("common.delete", "Delete")}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      <AddDriverDialog open={addOpen} onClose={() => setAddOpen(false)} />
      <SetCodeDialog driver={codeFor} onClose={() => setCodeFor(null)} />
      <DeleteDriverDialog driver={deleteFor} onClose={() => setDeleteFor(null)} />
    </>
  );
}

function AddDriverDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const create = useCreateDriver();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Reset the form each time the dialog opens.
  const [wasOpen, setWasOpen] = useState(false);
  if (open && !wasOpen) {
    setWasOpen(true);
    setName("");
    setPhone("");
    setCode("");
    setError(null);
    create.reset();
  }
  if (!open && wasOpen) setWasOpen(false);

  const codeInvalid = code.length > 0 && code.length < 6;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({
        name: name.trim(),
        phone: phone.trim() || undefined,
        access_code: code.trim() || undefined,
      });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("drivers.add_failed", "Could not add the driver."),
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{t("drivers.add_driver", "Add driver")}</DialogTitle>
            <DialogDescription>
              {t("drivers.add_desc", "Create a bus driver for your school. An access code lets them log into the driver app — you can set it now or later.")}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="d-name">{t("common.name", "Name")}</Label>
              <Input
                id="d-name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("drivers.name_placeholder", "e.g. Ravi Kumar")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="d-phone">
                {t("common.phone", "Phone")}{" "}
                <span className="font-normal text-muted-foreground">
                  {t("drivers.optional", "(optional)")}
                </span>
              </Label>
              <Input
                id="d-phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91…"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="d-code">
                {t("drivers.access_code", "Access code")}{" "}
                <span className="font-normal text-muted-foreground">
                  {t("drivers.optional_min6", "(optional, min 6)")}
                </span>
              </Label>
              <div className="flex gap-2">
                <Input
                  id="d-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder={t("drivers.code_placeholder", "Leave blank to set later")}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setCode(randomAccessCode())}
                >
                  {t("drivers.generate", "Generate")}
                </Button>
              </div>
              {codeInvalid && (
                <p className="text-xs text-destructive">
                  {t("drivers.code_too_short", "Access code must be at least 6 characters.")}
                </p>
              )}
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
              disabled={create.isPending}
            >
              {t("common.cancel", "Cancel")}
            </Button>
            <Button
              type="submit"
              disabled={create.isPending || !name.trim() || codeInvalid}
            >
              {create.isPending && <Loader2 className="size-4 animate-spin" />}
              {t("drivers.add_driver", "Add driver")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SetCodeDialog({
  driver,
  onClose,
}: {
  driver: Driver | null;
  onClose: () => void;
}) {
  const t = useT();
  const setCode = useSetDriverCode();
  const [code, setCodeValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [seededFor, setSeededFor] = useState<string | null>(null);
  if (driver && seededFor !== driver.id) {
    setSeededFor(driver.id);
    setCodeValue("");
    setError(null);
    setCode.reset();
  }

  const tooShort = code.length < 6;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!driver) return;
    setError(null);
    try {
      await setCode.mutateAsync({ id: driver.id, access_code: code.trim() });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("drivers.save_code_failed", "Could not save the access code."),
      );
    }
  };

  return (
    <Dialog open={driver !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>
              {driver?.has_access_code
                ? t("drivers.reset_access_code", "Reset access code")
                : t("drivers.set_access_code", "Set access code")}
            </DialogTitle>
            <DialogDescription>
              {driver?.name}
              {t("drivers.set_code_desc", " will use this code (with their phone) to log into the driver app. Share it with them securely.")}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 py-4">
            <Label htmlFor="set-code">{t("drivers.access_code_min6", "Access code (min 6)")}</Label>
            <div className="flex gap-2">
              <Input
                id="set-code"
                autoFocus
                value={code}
                onChange={(e) => setCodeValue(e.target.value)}
                placeholder={t("drivers.code_example", "e.g. 483920")}
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => setCodeValue(randomAccessCode())}
              >
                {t("drivers.generate", "Generate")}
              </Button>
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
              disabled={setCode.isPending}
            >
              {t("common.cancel", "Cancel")}
            </Button>
            <Button type="submit" disabled={setCode.isPending || tooShort}>
              {setCode.isPending && <Loader2 className="size-4 animate-spin" />}
              {t("drivers.save_code", "Save code")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function DeleteDriverDialog({
  driver,
  onClose,
}: {
  driver: Driver | null;
  onClose: () => void;
}) {
  const t = useT();
  const del = useDeleteDriver();
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    if (!driver) return;
    setError(null);
    try {
      await del.mutateAsync(driver.id);
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("drivers.delete_failed", "Could not delete the driver."),
      );
    }
  };

  return (
    <Dialog open={driver !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("drivers.delete_driver", "Delete driver")}</DialogTitle>
          <DialogDescription>
            {t("drivers.delete_prefix", "Delete")}{" "}
            <span className="font-medium">{driver?.name}</span>
            {t("drivers.delete_suffix", "? This revokes their access and can't be undone.")}
          </DialogDescription>
        </DialogHeader>
        {error && (
          <p className="text-sm font-medium text-destructive">{error}</p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={del.isPending}>
            {t("common.cancel", "Cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={confirm}
            disabled={del.isPending}
          >
            {del.isPending && <Loader2 className="size-4 animate-spin" />}
            {t("common.delete", "Delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
