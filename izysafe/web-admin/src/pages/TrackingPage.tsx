import { useEffect, useMemo, useRef, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Bus, MapPin, RefreshCw, Route as RouteIcon, User } from "lucide-react";
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
  useFleet,
  useRouteAssignments,
  type FleetBus,
} from "@/features/tracking/api";

const MAX_TRAIL = 25;
const ago = (iso: string | null) =>
  iso ? `${formatDistanceToNow(new Date(iso))} ago` : "never";

export function TrackingPage() {
  const fleet = useFleet(10_000);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const buses = useMemo(() => fleet.data ?? [], [fleet.data]);

  // Accumulate a short client-side trail per bus from successive polls
  // (bus positions aren't persisted server-side).
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

  const selected = buses.find((b) => b.bus_id === selectedId) ?? null;
  const online = buses.filter((b) => b.online).length;

  return (
    <>
      <PageHeader
        title="Live Tracking"
        description="Real-time positions of your school buses."
        actions={
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
              </span>
              Live · {online}/{buses.length} online
            </span>
            <Button
              variant="outline"
              onClick={() => fleet.refetch()}
              disabled={fleet.isFetching}
            >
              <RefreshCw
                className={fleet.isFetching ? "size-4 animate-spin" : "size-4"}
              />
              Refresh
            </Button>
          </div>
        }
      />

      {fleet.isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm font-medium text-destructive">
            {fleet.error instanceof ApiClientError
              ? fleet.error.message
              : "Failed to load live tracking."}
          </CardContent>
        </Card>
      )}

      {fleet.isLoading && (
        <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
          <Skeleton className="h-[72vh] w-full" />
          <Skeleton className="h-[72vh] w-full" />
        </div>
      )}

      {fleet.isSuccess && buses.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Bus className="size-9 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No buses registered yet. Add buses and routes to see them here.
            </p>
          </CardContent>
        </Card>
      )}

      {fleet.isSuccess && buses.length > 0 && (
        <>
          <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
            {/* Bus list */}
            <Card className="flex h-[72vh] flex-col overflow-hidden">
              <CardHeader className="border-b py-3">
                <CardTitle className="text-sm text-muted-foreground">
                  Buses ({buses.length})
                </CardTitle>
              </CardHeader>
              <div className="flex-1 space-y-2 overflow-y-auto p-3">
                {buses.map((b) => (
                  <BusRow
                    key={b.bus_id}
                    bus={b}
                    selected={b.bus_id === selectedId}
                    onSelect={() => setSelectedId(b.bus_id)}
                  />
                ))}
              </div>
            </Card>

            {/* Map */}
            <Card className="h-[72vh] overflow-hidden">
              <BusMap
                buses={buses}
                selectedId={selectedId}
                onSelect={setSelectedId}
                trail={selectedId ? trails.current[selectedId] ?? [] : []}
              />
            </Card>
          </div>

          {selected && <BusDetail bus={selected} />}
        </>
      )}
    </>
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
                      <TableCell className="font-medium">
                        {a.child_name}
                      </TableCell>
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

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-medium">{value}</p>
    </div>
  );
}
