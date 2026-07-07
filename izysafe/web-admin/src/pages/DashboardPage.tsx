import {
  Bus,
  ClipboardCheck,
  FileBarChart,
  MapPin,
  Navigation,
  UserCheck,
  Users,
  UserX,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "@/auth/useAuth";
import { useT } from "@/lib/i18n/I18nProvider";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardStats } from "@/features/dashboard/api";

interface Shortcut {
  titleKey: string;
  title: string;
  descKey: string;
  description: string;
  to: string;
  icon: LucideIcon;
}

const SHORTCUTS: Shortcut[] = [
  {
    titleKey: "dash.attendance",
    title: "Attendance",
    descKey: "dash.attendance_desc",
    description: "View the daily register and mark manual overrides.",
    to: "/attendance",
    icon: ClipboardCheck,
  },
  {
    titleKey: "dash.reports",
    title: "Reports",
    descKey: "dash.reports_desc",
    description: "Date-range attendance summaries and CSV export.",
    to: "/reports",
    icon: FileBarChart,
  },
  {
    titleKey: "dash.roster",
    title: "Roster",
    descKey: "dash.roster_desc",
    description: "Manage enrolled students and parent consent.",
    to: "/roster",
    icon: Users,
  },
  {
    titleKey: "dash.drivers",
    title: "Drivers",
    descKey: "dash.drivers_desc",
    description: "Manage bus drivers and their trip activity.",
    to: "/drivers",
    icon: Bus,
  },
];

export function DashboardPage() {
  const { admin } = useAuth();
  const t = useT();
  const stats = useDashboardStats();
  const greetingName = admin?.name ?? admin?.email ?? "";
  const s = stats.data;

  return (
    <>
      <PageHeader
        title={t("dashboard.title", "Dashboard")}
        description={`${t("dashboard.welcome", "Welcome back")}${greetingName ? `, ${greetingName}` : ""}.`}
      />

      {/* Live tracking hero */}
      <Link to="/tracking" className="group mb-6 block">
        <Card className="overflow-hidden border-0 bg-brand-gradient text-white shadow-md transition-shadow group-hover:shadow-lg">
          <CardContent className="flex flex-col items-start justify-between gap-4 py-6 sm:flex-row sm:items-center">
            <div className="flex items-center gap-4">
              <div className="flex size-12 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
                <MapPin className="size-6" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">{t("dash.live_tracking", "Live Tracking")}</h2>
                <p className="text-sm text-white/85">
                  {t("dash.live_tracking_desc", "See where every school bus and student is, in real time.")}
                </p>
              </div>
            </div>
            <Button
              variant="secondary"
              className="bg-white text-primary hover:bg-white/90"
            >
              {t("dash.open_live_map", "Open live map")}
            </Button>
          </CardContent>
        </Card>
      </Link>

      {/* Live stats */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={t("dash.buses_online", "Buses online")}
          value={s ? `${s.buses_online}/${s.buses_total}` : undefined}
          hint={s?.active_trips ? `${s.active_trips} ${t("dash.on_active_trips", "on active trips")}` : t("dash.of_your_fleet", "of your fleet")}
          icon={Bus}
          accent="text-primary"
          to="/tracking"
          loading={stats.isLoading}
        />
        <StatCard
          label={t("dash.present_today", "Present today")}
          value={s ? String(s.students_present) : undefined}
          hint={s ? `${t("dash.of", "of")} ${s.consented} ${t("dash.consented", "consented")}` : undefined}
          icon={UserCheck}
          accent="text-emerald-600"
          to="/attendance"
          loading={stats.isLoading}
        />
        <StatCard
          label={t("dash.pending_consents", "Pending consents")}
          value={s ? String(s.pending_consents) : undefined}
          hint={t("dash.awaiting_opt_in", "awaiting parent opt-in")}
          icon={UserX}
          accent="text-amber-600"
          to="/roster"
          loading={stats.isLoading}
        />
        <StatCard
          label={t("dash.active_trips", "Active trips")}
          value={s ? String(s.active_trips) : undefined}
          hint={s ? `${s.buses_total} ${t("dash.buses", "buses")}` : undefined}
          icon={Navigation}
          accent="text-brand-violet"
          to="/tracking"
          loading={stats.isLoading}
        />
      </div>

      {/* Quick links */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {SHORTCUTS.map(({ titleKey, title, descKey, description, to, icon: Icon }) => (
          <Link key={to} to={to} className="group">
            <Card className="h-full transition-colors group-hover:border-primary/50">
              <CardHeader className="space-y-3">
                <div className="flex size-9 items-center justify-center rounded-md bg-primary/10">
                  <Icon className="size-5 text-primary" />
                </div>
                <div>
                  <CardTitle className="text-base">{t(titleKey, title)}</CardTitle>
                  <CardDescription className="mt-1">
                    {t(descKey, description)}
                  </CardDescription>
                </div>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  accent,
  to,
  loading,
}: {
  label: string;
  value: string | undefined;
  hint?: string;
  icon: LucideIcon;
  accent: string;
  to: string;
  loading: boolean;
}) {
  return (
    <Link to={to} className="group">
      <Card className="transition-colors group-hover:border-primary/40">
        <CardContent className="flex items-center justify-between pt-6">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{label}</p>
            {loading || value === undefined ? (
              <Skeleton className="mt-1 h-8 w-16" />
            ) : (
              <p className="mt-0.5 text-3xl font-semibold tracking-tight">
                {value}
              </p>
            )}
            {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
          </div>
          <div className="flex size-10 items-center justify-center rounded-lg bg-muted">
            <Icon className={`size-5 ${accent}`} />
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
