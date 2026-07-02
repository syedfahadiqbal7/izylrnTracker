import {
  ClipboardCheck,
  FileBarChart,
  LayoutDashboard,
  MapPin,
  ScrollText,
  Settings,
  Truck,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Restricts the item to role='admin' (e.g. the audit trail). */
  adminOnly?: boolean;
  /** Exact-match the route (used for the index "/"). */
  end?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", to: "/", icon: LayoutDashboard, end: true },
  { label: "Live Tracking", to: "/tracking", icon: MapPin },
  { label: "Attendance", to: "/attendance", icon: ClipboardCheck },
  { label: "Reports", to: "/reports", icon: FileBarChart },
  { label: "Roster", to: "/roster", icon: Users },
  { label: "Drivers", to: "/drivers", icon: Truck },
  { label: "Audit", to: "/audit", icon: ScrollText, adminOnly: true },
  { label: "Settings", to: "/settings", icon: Settings },
];
