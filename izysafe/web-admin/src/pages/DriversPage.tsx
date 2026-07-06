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

function fmtLastLogin(iso: string | null) {
  return iso ? format(new Date(iso), "d MMM yyyy, HH:mm") : "Never";
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
            Add driver
          </Button>
        }
      />

      {drivers.isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm font-medium text-destructive">
            {drivers.error instanceof ApiClientError
              ? drivers.error.message
              : "Failed to load drivers."}
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
                  Add driver
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Phone</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Last login</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
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
                            {d.active ? "Active" : "Inactive"}
                          </Badge>
                          {!d.has_access_code && (
                            <Badge variant="warning" className="gap-1">
                              <ShieldAlert className="size-3" />
                              No code
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">
                        {fmtLastLogin(d.last_login_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="size-4" />
                              <span className="sr-only">Open actions</span>
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => setCodeFor(d)}>
                              <KeyRound className="size-4" />
                              {d.has_access_code
                                ? "Reset access code"
                                : "Set access code"}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              disabled={setActive.isPending}
                              onClick={() =>
                                setActive.mutate({ id: d.id, active: !d.active })
                              }
                            >
                              <Power className="size-4" />
                              {d.active ? "Deactivate" : "Reactivate"}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => setDeleteFor(d)}
                            >
                              <Trash2 className="size-4" />
                              Delete
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
          : "Could not add the driver.",
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Add driver</DialogTitle>
            <DialogDescription>
              Create a bus driver for your school. An access code lets them log
              into the driver app — you can set it now or later.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="d-name">Name</Label>
              <Input
                id="d-name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Ravi Kumar"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="d-phone">
                Phone{" "}
                <span className="font-normal text-muted-foreground">
                  (optional)
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
                Access code{" "}
                <span className="font-normal text-muted-foreground">
                  (optional, min 6)
                </span>
              </Label>
              <div className="flex gap-2">
                <Input
                  id="d-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="Leave blank to set later"
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setCode(randomAccessCode())}
                >
                  Generate
                </Button>
              </div>
              {codeInvalid && (
                <p className="text-xs text-destructive">
                  Access code must be at least 6 characters.
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
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={create.isPending || !name.trim() || codeInvalid}
            >
              {create.isPending && <Loader2 className="size-4 animate-spin" />}
              Add driver
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
          : "Could not save the access code.",
      );
    }
  };

  return (
    <Dialog open={driver !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>
              {driver?.has_access_code ? "Reset" : "Set"} access code
            </DialogTitle>
            <DialogDescription>
              {driver?.name} will use this code (with their phone) to log into
              the driver app. Share it with them securely.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 py-4">
            <Label htmlFor="set-code">Access code (min 6)</Label>
            <div className="flex gap-2">
              <Input
                id="set-code"
                autoFocus
                value={code}
                onChange={(e) => setCodeValue(e.target.value)}
                placeholder="e.g. 483920"
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => setCodeValue(randomAccessCode())}
              >
                Generate
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
              Cancel
            </Button>
            <Button type="submit" disabled={setCode.isPending || tooShort}>
              {setCode.isPending && <Loader2 className="size-4 animate-spin" />}
              Save code
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
          : "Could not delete the driver.",
      );
    }
  };

  return (
    <Dialog open={driver !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete driver</DialogTitle>
          <DialogDescription>
            Delete <span className="font-medium">{driver?.name}</span>? This
            revokes their access and can't be undone.
          </DialogDescription>
        </DialogHeader>
        {error && (
          <p className="text-sm font-medium text-destructive">{error}</p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={del.isPending}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={confirm}
            disabled={del.isPending}
          >
            {del.isPending && <Loader2 className="size-4 animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
