import {
  ClipboardCheck,
  FileBarChart,
  Truck,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "@/auth/useAuth";
import { PageHeader } from "@/components/PageHeader";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface Shortcut {
  title: string;
  description: string;
  to: string;
  icon: LucideIcon;
}

const SHORTCUTS: Shortcut[] = [
  {
    title: "Attendance",
    description: "View the daily register and mark manual overrides.",
    to: "/attendance",
    icon: ClipboardCheck,
  },
  {
    title: "Reports",
    description: "Date-range attendance summaries and CSV export.",
    to: "/reports",
    icon: FileBarChart,
  },
  {
    title: "Roster",
    description: "Manage enrolled students and parent consent.",
    to: "/roster",
    icon: Users,
  },
  {
    title: "Drivers",
    description: "Manage bus drivers and their trip activity.",
    to: "/drivers",
    icon: Truck,
  },
];

export function DashboardPage() {
  const { admin } = useAuth();
  const greetingName = admin?.name ?? admin?.email ?? "";

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`Welcome back${greetingName ? `, ${greetingName}` : ""}.`}
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {SHORTCUTS.map(({ title, description, to, icon: Icon }) => (
          <Link key={to} to={to} className="group">
            <Card className="h-full transition-colors group-hover:border-primary/50">
              <CardHeader className="space-y-3">
                <div className="flex size-9 items-center justify-center rounded-md bg-primary/10">
                  <Icon className="size-5 text-primary" />
                </div>
                <div>
                  <CardTitle className="text-base">{title}</CardTitle>
                  <CardDescription className="mt-1">
                    {description}
                  </CardDescription>
                </div>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Getting started</CardTitle>
          <CardDescription>
            This is the initial panel shell. Pages are being built out
            slice-by-slice — attendance reporting/export is next, wired to the
            Sprint 10 backend endpoints.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Signed in as <span className="font-medium">{admin?.email}</span> (
          {admin?.role}).
        </CardContent>
      </Card>
    </>
  );
}
