import { useEffect, useMemo, useRef, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import {
  Battery,
  Bus,
  Clock,
  MapPin,
  RefreshCw,
  Route as RouteIcon,
  User,
  UserRound,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { ApiClientError } from "@/types/api";
import { BusMap } from "@/features/tracking/BusMap";
import {
  useChildrenFleet,
  useFleet,
  useRouteAssignments,
  type FleetBus,
  type LiveChild,
} from "@/features/tracking/api";

const MAX_TRAIL = 25;
const ago = (iso: string | null) =>
  iso ? `${formatDistanceToNow(new Date(iso))} ago` : "never";

export function TrackingPage() {
  const fleet = useFleet(10_000);
  const children = useChildrenFleet(10_000);
  const [selectedBus, setSelectedBus] = useState<string | null>(null);
  const [selectedChild, setSelectedChild] = useState<string | null>(null);
  const [showBuses, setShowBuses] = useState(true);
  const [showChildren, setShowChildren] = useState(true);

  const buses = useMemo(() => fleet.data ?? [], [fleet.data]);
  const kids = useMemo(() => children.data ?? [], [children.data]);

  // Short client-side trail per bus from successive polls.
  const trails = useRef<Record<string, [number, number][]>>({});
  useEffect(() => {
    for (const b of buses) {
      if (!b.position) continue;
      const pt: [number, number] = [b.position.lat, b.position.lng];
      const t = trails.current[b.bus_id] ?? [];
      const last = t[t.length - 1];
      if (!last || last[0] !== pt[0] || last[1] !== pt[1]) {
        trails.current[b.bus_id] = [...t, pt].slice(-MAX_TRAIL);
      }
    }
  }, [buses]);

  const pickBus = (id: string) => {
    setSelectedBus(id);
    setSelectedChild(null);
  };
  const pickChild = (id: string) => {
    setSelectedChild(id);
    setSelectedBus(null);
  };

  const bus = buses.find((b) => b.bus_id === selectedBus) ?? null;
  const child = kids.find((c) => c.child_id === selectedChild) ?? null;
  const onlineBuses = buses.filter((b) => b.online).length;
  const onlineKids = kids.filter((c) => c.online).length;
  const loading = fleet.isLoading || children.isLoading;
  const anyData = buses.length > 0 || kids.length > 0;

  return (
    <>
      <PageHeader
        title="Live Tracking"
        description="Real-time positions of your school buses and students."
        actions={
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
              </span>
              Live
            </span>
            <Button
              variant="outline"
              onClick={() => {
                fleet.refetch();
                children.refetch();
              }}
              disabled={fleet.isFetching || children.isFetching}
            >
              <RefreshCw
                className={
                  fleet.isFetching || children.isFetching
                    ? "size-4 animate-spin"
                    : "size-4"
                }
              />
              Refresh
            </Button>
          </div>
        }
      />

      {(fleet.isError || children.isError) && (
        <Card>
          <CardContent className="py-12 text-center text-sm font-medium text-destructive">
            {fleet.error instanceof ApiClientError
              ? fleet.error.message
              : "Failed to load live tracking."}
          </CardContent>
        </Card>
      )}

      {loading && (
        <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
          <Skeleton className="h-[72vh] w-full" />
          <Skeleton className="h-[72vh] w-full" />
        </div>
      )}

      {!loading && !anyData && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <MapPin className="size-9 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Nothing to track yet. Register buses or enable location consent for
              students to see them here.
            </p>
          </CardContent>
        </Card>
      )}

      {!loading && anyData && (
        <>
          <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
            {/* List + layer toggles */}
            <Card className="flex h-[72vh] flex-col overflow-hidden">
              <CardHeader className="gap-2 border-b py-3">
                <div className="flex gap-2">
                  <LayerToggle
                    color="#2C56EE"
                    label="Buses"
                    count={`${onlineBuses}/${buses.length}`}
                    on={showBuses}
                    onClick={() => setShowBuses((v) => !v)}
                  />
                  <LayerToggle
                    color="#8D03E0"
                    label="Students"
                    count={`${onlineKids}/${kids.length}`}
                    on={showChildren}
                    onClick={() => setShowChildren((v) => !v)}
                  />
                </div>
              </CardHeader>
              <div className="flex-1 space-y-4 overflow-y-auto p-3">
                {showBuses && buses.length > 0 && (
                  <Section title="Buses">
                    {buses.map((b) => (
                      <BusRow
                        key={b.bus_id}
                        bus={b}
                        selected={b.bus_id === selectedBus}
                        onSelect={() => pickBus(b.bus_id)}
                      />
                    ))}
                  </Section>
                )}
                {showChildren && kids.length > 0 && (
                  <Section title="Students">
                    {kids.map((c) => (
                      <ChildRow
                        key={c.child_id}
                        child={c}
                        selected={c.child_id === selectedChild}
                        onSelect={() => pickChild(c.child_id)}
                      />
                    ))}
                  </Section>
                )}
              </div>
            </Card>

            {/* Map */}
            <Card className="h-[72vh] overflow-hidden">
              <BusMap
                buses={buses}
                children={kids}
                showBuses={showBuses}
                showChildren={showChildren}
                selectedId={selectedBus}
                selectedChildId={selectedChild}
                onSelect={pickBus}
                onSelectChild={pickChild}
                trail={selectedBus ? trails.current[selectedBus] ?? [] : []}
              />
            </Card>
          </div>

          {bus && <BusDetail bus={bus} />}
          {child && <ChildDetail child={child} />}
        </>
      )}
    </>
  );
}

function LayerToggle({
  color,
  label,
  count,
  on,
  onClick,
}: {
  color: string;
  label: string;
  count: string;
  on: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex flex-1 items-center justify-center gap-2 rounded-md border px-2 py-1.5 text-sm font-medium transition-colors",
        on ? "bg-background" : "bg-muted/50 text-muted-foreground opacity-60",
      )}
    >
      <span
        className="size-2.5 rounded-full"
        style={{ background: on ? color : "#cbd5e1" }}
      />
      {label} <span className="text-xs text-muted-foreground">{count}</span>
    </button>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <p className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  );
}

function BusRow({
  bus,
  selected,
  onSelect,
}: {
  bus: FleetBus;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-colors",
        selected
          ? "border-primary/50 bg-primary/5"
          : "hover:border-primary/30 hover:bg-muted/50",
      )}
    >
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 font-medium">
          <Bus className="size-4 text-primary" />
          {bus.bus_name}
        </span>
        <Badge variant={bus.online ? "success" : "muted"}>
          {bus.online ? "Online" : "Offline"}
        </Badge>
      </div>
      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <RouteIcon className="size-3" />
          {bus.route ? bus.route.name : "No route"}
          {bus.trip?.active && (
            <Badge variant="secondary" className="ml-1 py-0 text-[10px]">
              Trip active
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <User className="size-3" />
          {bus.driver ? bus.driver.name : "No driver"}
          {bus.route ? ` · ${bus.route.students} students` : ""}
        </div>
        <div className="flex items-center gap-1.5">
          <MapPin className="size-3" />
          {bus.position ? `Updated ${ago(bus.position.timestamp)}` : "No GPS fix"}
        </div>
      </div>
    </button>
  );
}

function ChildRow({
  child,
  selected,
  onSelect,
}: {
  child: LiveChild;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-colors",
        selected
          ? "border-brand-violet/50 bg-brand-violet/5"
          : "hover:border-brand-violet/30 hover:bg-muted/50",
      )}
    >
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 font-medium">
          <UserRound className="size-4 text-brand-violet" />
          {child.child_name}
        </span>
        <Badge variant={child.online ? "success" : "muted"}>
          {child.online ? "Online" : "Offline"}
        </Badge>
      </div>
      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          {child.class_grade ?? "—"}
          {child.battery != null && (
            <span className="flex items-center gap-1">
              <Battery className="size-3" />
              {child.battery}%
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <MapPin className="size-3" />
          {!child.in_window
            ? "Live location paused (outside school hours)"
            : child.position
              ? `Updated ${ago(child.position.timestamp)}`
              : "No GPS fix"}
        </div>
      </div>
    </button>
  );
}

function BusDetail({ bus }: { bus: FleetBus }) {
  const assignments = useRouteAssignments(bus.route?.id ?? null);
  const stopName = useMemo(() => {
    const m: Record<string, string> = {};
    for (const s of bus.route?.stops ?? []) m[s.id] = `Stop ${s.seq} · ${s.name}`;
    return m;
  }, [bus.route]);

  return (
    <Card className="mt-4">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Bus className="size-4 text-primary" />
          {bus.bus_name}
          <Badge variant={bus.online ? "success" : "muted"} className="ml-1">
            {bus.online ? "Online" : "Offline"}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-4">
          <Detail label="Route" value={bus.route?.name ?? "—"} />
          <Detail label="Driver" value={bus.driver?.name ?? "—"} />
          <Detail
            label="Trip"
            value={
              bus.trip?.active
                ? `Active · started ${ago(bus.trip.started_at)}`
                : "No active trip"
            }
          />
          <Detail label="Last seen" value={ago(bus.last_seen)} />
        </div>

        {bus.route && (
          <div>
            <p className="mb-2 text-sm font-medium">
              Assigned students ({bus.route.students})
            </p>
            {assignments.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : (assignments.data?.length ?? 0) === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">
                No students assigned to this route.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Student</TableHead>
                    <TableHead>Boarding stop</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {assignments.data!.map((a) => (
                    <TableRow key={a.id}>
                      <TableCell className="font-medium">{a.child_name}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {a.stop_id ? stopName[a.stop_id] ?? "—" : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ChildDetail({ child }: { child: LiveChild }) {
  return (
    <Card className="mt-4">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <UserRound className="size-4 text-brand-violet" />
          {child.child_name}
          <Badge variant={child.online ? "success" : "muted"} className="ml-1">
            {child.online ? "Online" : "Offline"}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-4">
          <Detail label="Class / grade" value={child.class_grade ?? "—"} />
          <Detail label="Device" value={child.device_name ?? "—"} />
          <Detail
            label="Battery"
            value={child.battery != null ? `${child.battery}%` : "—"}
          />
          <Detail label="Last seen" value={ago(child.last_seen)} />
        </div>
        {!child.in_window && (
          <p className="flex items-center gap-1.5 rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
            <Clock className="size-4" />
            Live location is only shown during school hours on school days.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-medium">{value}</p>
    </div>
  );
}
