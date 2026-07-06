/**
 * Static navigation fallback. The live sidebar is driven by admin-managed menu_items
 * (GET /schools/menu); this list only backstops the UI if that request fails. `labelKey`
 * + `iconName` mirror the seeded menu rows so the fallback looks identical.
 */
export interface NavItem {
  /** Translation key for the label (e.g. "nav.dashboard"). */
  labelKey: string;
  to: string;
  /** Lucide icon name resolved via features/navigation/icons. */
  iconName: string;
  /** Restricts the item to role='admin' (e.g. the audit trail + menu management). */
  adminOnly?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { labelKey: "nav.dashboard", to: "/", iconName: "LayoutDashboard" },
  { labelKey: "nav.tracking", to: "/tracking", iconName: "MapPin" },
  { labelKey: "nav.attendance", to: "/attendance", iconName: "ClipboardCheck" },
  { labelKey: "nav.reports", to: "/reports", iconName: "FileBarChart" },
  { labelKey: "nav.roster", to: "/roster", iconName: "Users" },
  { labelKey: "nav.routes", to: "/routes", iconName: "Route" },
  { labelKey: "nav.drivers", to: "/drivers", iconName: "Truck" },
  { labelKey: "nav.audit", to: "/audit", iconName: "ScrollText", adminOnly: true },
  { labelKey: "nav.menus", to: "/menus", iconName: "ListTree", adminOnly: true },
  { labelKey: "nav.settings", to: "/settings", iconName: "Settings" },
];
