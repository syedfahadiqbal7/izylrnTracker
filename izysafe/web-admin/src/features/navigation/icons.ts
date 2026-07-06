/**
 * Maps the `icon` string stored on a menu_item (a lucide icon name, set by admins in the
 * Menu Management UI) to the actual lucide component. Unknown names fall back to a dot so
 * a mistyped icon never breaks the sidebar.
 */
import {
  Circle,
  ClipboardCheck,
  FileBarChart,
  LayoutDashboard,
  ListTree,
  MapPin,
  Route,
  ScrollText,
  Settings,
  Truck,
  Users,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  LayoutDashboard,
  MapPin,
  ClipboardCheck,
  FileBarChart,
  Users,
  Route,
  Truck,
  ScrollText,
  ListTree,
  Settings,
};

/** The icon names an admin can pick from in the Menu Management editor. */
export const ICON_NAMES = Object.keys(ICONS);

export function resolveIcon(name: string | null | undefined): LucideIcon {
  return (name && ICONS[name]) || Circle;
}
