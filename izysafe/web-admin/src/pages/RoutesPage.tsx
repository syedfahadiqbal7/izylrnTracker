import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Bus,
  ChevronDown,
  ChevronUp,
  Loader2,
  Pencil,
  Plus,
  Route as RouteIcon,
  Trash2,
  UserPlus,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { ApiClientError } from "@/types/api";
import { useDrivers } from "@/features/drivers/api";
import { useRoster } from "@/features/roster/api";
import { RouteStopsMap } from "@/features/routes/RouteStopsMap";
import {
  useAddStop,
  useAssignStudent,
  useAssignments,
  useBuses,
  useCreateRoute,
  useDeleteBus,
  useDeleteRoute,
  useDeleteStop,
  useRegisterBus,
  useReorderStops,
  useRoutes,
  useStops,
  useUnassign,
  useUpdateRoute,
  useUpdateStop,
  type BusDevice,
  type Route,
  type Stop,
} from "@/features/routes/api";

const NONE = "__none__";

export function RoutesPage() {
  return (
    <>
      <PageHeader
        title="Routes & Buses"
        description="Bus devices, routes, stops, and student assignments."
      />
      <Tabs defaultValue="routes">
        <TabsList>
          <TabsTrigger value="routes">
            <RouteIcon className="size-4" />
            Routes
          </TabsTrigger>
          <TabsTrigger value="buses">
            <Bus className="size-4" />
            Buses
          </TabsTrigger>
        </TabsList>
        <TabsContent value="routes">
          <RoutesTab />
        </TabsContent>
        <TabsContent value="buses">
          <BusesTab />
        </TabsContent>
      </Tabs>
    </>
  );
}

// --------------------------------------------------------------------------- //
// Routes tab (master-detail)
// --------------------------------------------------------------------------- //
function RoutesTab() {
  const routes = useRoutes();
  const buses = useBuses();
  const drivers = useDrivers();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [routeDialog, setRouteDialog] = useState<{ route: Route | null } | null>(
    null,
  );

  const list = routes.data ?? [];
  useEffect(() => {
    if (list.length && !list.some((r) => r.id === selectedId)) {
      setSelectedId(list[0].id);
    }
  }, [list, selectedId]);
  const selected = list.find((r) => r.id === selectedId) ?? null;

  const busName = (id: string | null) =>
    buses.data?.find((b) => b.id === id)?.name ?? null;
  const driverName = (id: string | null) =>
    drivers.data?.find((d) => d.id === id)?.name ?? null;

  return (
    <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
      {/* Route list */}
      <Card className="flex h-fit flex-col">
        <CardHeader className="flex-row items-center justify-between border-b py-3">
          <CardTitle className="text-sm text-muted-foreground">
            Routes ({list.length})
          </CardTitle>
          <Button size="sm" onClick={() => setRouteDialog({ route: null })}>
            <Plus className="size-4" />
            New
          </Button>
        </CardHeader>
        <div className="space-y-2 p-3">
          {routes.isLoading &&
            Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          {routes.isSuccess && list.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No routes yet. Create your first route.
            </p>
          )}
          {list.map((r) => (
            <button
              key={r.id}
              onClick={() => setSelectedId(r.id)}
              className={cn(
                "w-full rounded-lg border p-3 text-left transition-colors",
                r.id === selectedId
                  ? "border-primary/50 bg-primary/5"
                  : "hover:border-primary/30 hover:bg-muted/50",
              )}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{r.name}</span>
                {!r.active && <Badge variant="muted">Inactive</Badge>}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {busName(r.device_id) ?? "No bus"} ·{" "}
                {driverName(r.driver_id) ?? "No driver"}
              </p>
            </button>
          ))}
        </div>
      </Card>

      {/* Selected route detail */}
      {selected ? (
        <RouteDetail
          route={selected}
          busName={busName(selected.device_id)}
          driverName={driverName(selected.driver_id)}
          onEdit={() => setRouteDialog({ route: selected })}
        />
      ) : (
        <Card>
          <CardContent className="py-16 text-center text-sm text-muted-foreground">
            Select or create a route to manage its stops and students.
          </CardContent>
        </Card>
      )}

      {routeDialog && (
        <RouteDialog
          route={routeDialog.route}
          buses={buses.data ?? []}
          drivers={drivers.data ?? []}
          onClose={() => setRouteDialog(null)}
          onCreated={(id) => setSelectedId(id)}
        />
      )}
    </div>
  );
}

function RouteDetail({
  route,
  busName,
  driverName,
  onEdit,
}: {
  route: Route;
  busName: string | null;
  driverName: string | null;
  onEdit: () => void;
}) {
  const del = useDeleteRoute();
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-start justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              {route.name}
              {!route.active && <Badge variant="muted">Inactive</Badge>}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Bus: {busName ?? "—"} · Driver: {driverName ?? "—"}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onEdit}>
              <Pencil className="size-4" />
              Edit
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 className="size-4" />
              Delete
            </Button>
          </div>
        </CardHeader>
      </Card>

      <StopsPanel route={route} />
      <AssignmentsPanel route={route} />

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete route"
        description={`Delete "${route.name}"? Its stops and student assignments will be removed.`}
        confirmLabel="Delete"
        destructive
        onConfirm={() => del.mutateAsync(route.id).then(() => undefined)}
      />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Stops
// --------------------------------------------------------------------------- //
function StopsPanel({ route }: { route: Route }) {
  const stops = useStops(route.id);
  const reorder = useReorderStops();
  const del = useDeleteStop();
  const [stopDialog, setStopDialog] = useState<{
    stop: Stop | null;
    lat?: number;
    lng?: number;
  } | null>(null);
  const [deleteStop, setDeleteStop] = useState<Stop | null>(null);

  const rows = stops.data ?? [];
  const nextSeq = (rows.at(-1)?.seq ?? 0) + 1;

  const move = (index: number, dir: -1 | 1) => {
    const order = rows.map((s) => s.id);
    const j = index + dir;
    if (j < 0 || j >= order.length) return;
    [order[index], order[j]] = [order[j], order[index]];
    reorder.mutate({ routeId: route.id, stop_ids: order });
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-3">
        <CardTitle className="text-base">Stops ({rows.length})</CardTitle>
        <Button size="sm" onClick={() => setStopDialog({ stop: null })}>
          <Plus className="size-4" />
          Add stop
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="h-72 overflow-hidden rounded-lg border">
          <RouteStopsMap
            stops={rows}
            onAddAt={(lat, lng) => setStopDialog({ stop: null, lat, lng })}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Tip: click anywhere on the map to drop a new stop there.
        </p>

        {rows.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No stops yet. Add stops in boarding order.
          </p>
        ) : (
          <div className="divide-y rounded-lg border">
            {rows.map((s, i) => (
              <div key={s.id} className="flex items-center gap-3 p-2.5">
                <Badge className="size-6 justify-center rounded-full p-0">
                  {s.seq}
                </Badge>
                <div className="flex-1">
                  <p className="text-sm font-medium">{s.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {s.lat.toFixed(5)}, {s.lng.toFixed(5)}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    disabled={i === 0 || reorder.isPending}
                    onClick={() => move(i, -1)}
                  >
                    <ChevronUp className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    disabled={i === rows.length - 1 || reorder.isPending}
                    onClick={() => move(i, 1)}
                  >
                    <ChevronDown className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    onClick={() => setStopDialog({ stop: s })}
                  >
                    <Pencil className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7 text-destructive"
                    onClick={() => setDeleteStop(s)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      {stopDialog && (
        <StopDialog
          routeId={route.id}
          stop={stopDialog.stop}
          initialLat={stopDialog.lat}
          initialLng={stopDialog.lng}
          nextSeq={nextSeq}
          onClose={() => setStopDialog(null)}
        />
      )}
      <ConfirmDialog
        open={deleteStop !== null}
        onOpenChange={(o) => !o && setDeleteStop(null)}
        title="Delete stop"
        description={`Remove stop "${deleteStop?.name}"?`}
        confirmLabel="Delete"
        destructive
        onConfirm={() =>
          del.mutateAsync(deleteStop!.id).then(() => setDeleteStop(null))
        }
      />
    </Card>
  );
}

function StopDialog({
  routeId,
  stop,
  initialLat,
  initialLng,
  nextSeq,
  onClose,
}: {
  routeId: string;
  stop: Stop | null;
  initialLat?: number;
  initialLng?: number;
  nextSeq: number;
  onClose: () => void;
}) {
  const add = useAddStop();
  const update = useUpdateStop();
  const editing = stop !== null;
  const [name, setName] = useState(stop?.name ?? "");
  const [lat, setLat] = useState(
    String(stop?.lat ?? initialLat ?? ""),
  );
  const [lng, setLng] = useState(String(stop?.lng ?? initialLng ?? ""));
  const [error, setError] = useState<string | null>(null);
  const pending = add.isPending || update.isPending;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const latN = Number(lat);
    const lngN = Number(lng);
    if (Number.isNaN(latN) || Number.isNaN(lngN)) {
      setError("Enter valid coordinates.");
      return;
    }
    try {
      if (editing) {
        await update.mutateAsync({ id: stop.id, name: name.trim(), lat: latN, lng: lngN });
      } else {
        await add.mutateAsync({
          routeId,
          name: name.trim(),
          lat: latN,
          lng: lngN,
          seq: nextSeq,
        });
      }
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError ? err.message : "Could not save the stop.",
      );
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{editing ? "Edit stop" : "Add stop"}</DialogTitle>
            <DialogDescription>
              {editing
                ? "Update this stop's name or location."
                : "New stops are added to the end of the route; reorder them afterwards."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="st-name">Name</Label>
              <Input
                id="st-name"
                required
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Main Gate"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="st-lat">Latitude</Label>
                <Input
                  id="st-lat"
                  required
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                  placeholder="18.5204"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="st-lng">Longitude</Label>
                <Input
                  id="st-lng"
                  required
                  value={lng}
                  onChange={(e) => setLng(e.target.value)}
                  placeholder="73.8567"
                />
              </div>
            </div>
            {error && (
              <p className="text-sm font-medium text-destructive">{error}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending || !name.trim()}>
              {pending && <Loader2 className="size-4 animate-spin" />}
              {editing ? "Save" : "Add stop"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------- //
// Assignments
// --------------------------------------------------------------------------- //
function AssignmentsPanel({ route }: { route: Route }) {
  const assignments = useAssignments(route.id);
  const stops = useStops(route.id);
  const unassign = useUnassign();
  const [assignOpen, setAssignOpen] = useState(false);
  const [removeFor, setRemoveFor] = useState<string | null>(null);

  const rows = assignments.data ?? [];
  const stopName = useMemo(() => {
    const m: Record<string, string> = {};
    for (const s of stops.data ?? []) m[s.id] = `Stop ${s.seq} · ${s.name}`;
    return m;
  }, [stops.data]);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-3">
        <CardTitle className="text-base">
          Assigned students ({rows.length})
        </CardTitle>
        <Button size="sm" onClick={() => setAssignOpen(true)}>
          <UserPlus className="size-4" />
          Assign student
        </Button>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No students assigned. Only consented students can be assigned.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Student</TableHead>
                <TableHead>Boarding stop</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium">{a.child_name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {a.stop_id ? stopName[a.stop_id] ?? "—" : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive"
                      onClick={() => setRemoveFor(a.id)}
                    >
                      Remove
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {assignOpen && (
        <AssignDialog
          route={route}
          stops={stops.data ?? []}
          assigned={rows.map((a) => a.child_id)}
          onClose={() => setAssignOpen(false)}
        />
      )}
      <ConfirmDialog
        open={removeFor !== null}
        onOpenChange={(o) => !o && setRemoveFor(null)}
        title="Remove student"
        description="Remove this student from the route?"
        confirmLabel="Remove"
        destructive
        onConfirm={() =>
          unassign.mutateAsync(removeFor!).then(() => setRemoveFor(null))
        }
      />
    </Card>
  );
}

function AssignDialog({
  route,
  stops,
  assigned,
  onClose,
}: {
  route: Route;
  stops: Stop[];
  assigned: string[];
  onClose: () => void;
}) {
  const roster = useRoster({ opted_in: true, limit: 200, offset: 0 });
  const assign = useAssignStudent();
  const [enrollmentId, setEnrollmentId] = useState("");
  const [stopId, setStopId] = useState<string>(NONE);
  const [error, setError] = useState<string | null>(null);

  const eligible = (roster.data?.items ?? []).filter(
    (e) => !assigned.includes(e.child_id),
  );

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await assign.mutateAsync({
        routeId: route.id,
        enrollment_id: enrollmentId,
        stop_id: stopId === NONE ? null : stopId,
      });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError ? err.message : "Could not assign the student.",
      );
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Assign student</DialogTitle>
            <DialogDescription>
              Assign a consented student to {route.name} and their boarding stop.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Student</Label>
              <Select value={enrollmentId} onValueChange={setEnrollmentId}>
                <SelectTrigger>
                  <SelectValue
                    placeholder={
                      eligible.length ? "Select a student" : "No eligible students"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {eligible.map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {e.child_name}
                      {e.class_grade ? ` · ${e.class_grade}` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {roster.isSuccess && eligible.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  All consented students are already assigned, or none exist yet.
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label>Boarding stop (optional)</Label>
              <Select value={stopId} onValueChange={setStopId}>
                <SelectTrigger>
                  <SelectValue placeholder="No specific stop" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>No specific stop</SelectItem>
                  {stops.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      Stop {s.seq} · {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {error && (
              <p className="text-sm font-medium text-destructive">{error}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={assign.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={assign.isPending || !enrollmentId}>
              {assign.isPending && <Loader2 className="size-4 animate-spin" />}
              Assign
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------- //
// Route create / edit dialog
// --------------------------------------------------------------------------- //
function RouteDialog({
  route,
  buses,
  drivers,
  onClose,
  onCreated,
}: {
  route: Route | null;
  buses: BusDevice[];
  drivers: { id: string; name: string }[];
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const create = useCreateRoute();
  const update = useUpdateRoute();
  const editing = route !== null;
  const [name, setName] = useState(route?.name ?? "");
  const [device, setDevice] = useState(route?.device_id ?? NONE);
  const [driver, setDriver] = useState(route?.driver_id ?? NONE);
  const [active, setActive] = useState(route?.active ?? true);
  const [error, setError] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const payload = {
      name: name.trim(),
      device_id: device === NONE ? null : device,
      driver_id: driver === NONE ? null : driver,
    };
    try {
      if (editing) {
        await update.mutateAsync({ id: route.id, ...payload, active });
      } else {
        const created = await create.mutateAsync(payload);
        onCreated(created.id);
      }
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError ? err.message : "Could not save the route.",
      );
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{editing ? "Edit route" : "New route"}</DialogTitle>
            <DialogDescription>
              A route links a bus and driver, with an ordered set of stops.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="rt-name">Name</Label>
              <Input
                id="rt-name"
                required
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Route A — North"
              />
            </div>
            <div className="space-y-2">
              <Label>Bus</Label>
              <Select value={device} onValueChange={setDevice}>
                <SelectTrigger>
                  <SelectValue placeholder="No bus" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>No bus</SelectItem>
                  {buses.map((b) => (
                    <SelectItem key={b.id} value={b.id}>
                      {b.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Driver</Label>
              <Select value={driver} onValueChange={setDriver}>
                <SelectTrigger>
                  <SelectValue placeholder="No driver" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>No driver</SelectItem>
                  {drivers.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {editing && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={active}
                  onChange={(e) => setActive(e.target.checked)}
                  className="size-4 accent-primary"
                />
                Route is active
              </label>
            )}
            {error && (
              <p className="text-sm font-medium text-destructive">{error}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending || !name.trim()}>
              {pending && <Loader2 className="size-4 animate-spin" />}
              {editing ? "Save" : "Create route"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------- //
// Buses tab
// --------------------------------------------------------------------------- //
function BusesTab() {
  const buses = useBuses();
  const del = useDeleteBus();
  const [addOpen, setAddOpen] = useState(false);
  const [removeFor, setRemoveFor] = useState<BusDevice | null>(null);

  const rows = buses.data ?? [];

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-3">
        <CardTitle className="text-base">Bus devices ({rows.length})</CardTitle>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="size-4" />
          Register bus
        </Button>
      </CardHeader>
      <CardContent>
        {buses.isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <Bus className="size-9 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No bus devices yet. Register a GPS tracker to start tracking.
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>IMEI</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((b) => (
                <TableRow key={b.id}>
                  <TableCell className="font-medium">
                    <span className="flex items-center gap-2">
                      <Bus className="size-4 text-primary" />
                      {b.name}
                    </span>
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {b.imei}
                  </TableCell>
                  <TableCell>
                    <Badge variant={b.is_online ? "success" : "muted"}>
                      {b.is_online ? "Online" : "Offline"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive"
                      onClick={() => setRemoveFor(b)}
                    >
                      <Trash2 className="size-4" />
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {addOpen && <BusDialog onClose={() => setAddOpen(false)} />}
      <ConfirmDialog
        open={removeFor !== null}
        onOpenChange={(o) => !o && setRemoveFor(null)}
        title="Delete bus"
        description={
          <>
            Delete <span className="font-medium">{removeFor?.name}</span>? Any
            route using it will keep working without a bus until you assign a new
            one.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={() =>
          del.mutateAsync(removeFor!.id).then(() => setRemoveFor(null))
        }
      />
    </Card>
  );
}

function BusDialog({ onClose }: { onClose: () => void }) {
  const register = useRegisterBus();
  const [name, setName] = useState("");
  const [imei, setImei] = useState("");
  const [traccarId, setTraccarId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await register.mutateAsync({
        name: name.trim(),
        imei: imei.trim(),
        traccar_id: traccarId.trim() ? Number(traccarId) : null,
      });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError ? err.message : "Could not register the bus.",
      );
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Register bus</DialogTitle>
            <DialogDescription>
              Register a bus GPS tracker so its live position appears on the map.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="bus-name">Name</Label>
              <Input
                id="bus-name"
                required
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Bus 12"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="bus-imei">IMEI</Label>
              <Input
                id="bus-imei"
                required
                value={imei}
                onChange={(e) => setImei(e.target.value)}
                placeholder="GPS tracker IMEI"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="bus-traccar">
                Traccar ID{" "}
                <span className="font-normal text-muted-foreground">
                  (optional)
                </span>
              </Label>
              <Input
                id="bus-traccar"
                value={traccarId}
                onChange={(e) => setTraccarId(e.target.value)}
                placeholder="Numeric device id in Traccar"
              />
            </div>
            {error && (
              <p className="text-sm font-medium text-destructive">{error}</p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={register.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={register.isPending || !name.trim() || !imei.trim()}>
              {register.isPending && <Loader2 className="size-4 animate-spin" />}
              Register
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
