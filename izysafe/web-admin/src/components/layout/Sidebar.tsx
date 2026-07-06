import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { useAuth } from "@/auth/useAuth";
import { useT } from "@/lib/i18n/I18nProvider";
import { fetchMenu, type MenuNavItem } from "@/features/navigation/api";
import { resolveIcon } from "@/features/navigation/icons";
import { Skeleton } from "@/components/ui/skeleton";
import { NAV_ITEMS } from "./nav";

/** Static fallback so the panel is never left without navigation if the menu API is
 *  slow or unreachable — mirrors the seeded menu_items. */
function fallbackItems(role: string | undefined): MenuNavItem[] {
  return NAV_ITEMS.filter((i) => !i.adminOnly || role === "admin").map((i) => ({
    item_key: i.to,
    label_key: i.labelKey,
    icon: i.iconName,
    path: i.to,
  }));
}

/** The shared sidebar contents (logo + dynamic nav + footer), used by both the fixed
 *  desktop sidebar and the mobile drawer. Menu items are admin-managed (GET /schools/menu). */
export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { admin } = useAuth();
  const t = useT();
  const menuQuery = useQuery({ queryKey: ["menu", "nav"], queryFn: fetchMenu });

  const items = menuQuery.data ?? (menuQuery.isError ? fallbackItems(admin?.role) : null);

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex h-16 items-center gap-2.5 border-b border-sidebar-border px-5">
        <img
          src="/izylrn-icon.png"
          alt="izyLrn"
          className="size-8 shrink-0 object-contain"
        />
        <span className="text-lg font-extrabold tracking-tight">
          izy<span className="text-brand-cyan">Lrn</span>
        </span>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {items === null
          ? Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full rounded-lg bg-sidebar-accent/40" />
            ))
          : items.map((item) => {
              const Icon = resolveIcon(item.icon);
              return (
                <NavLink
                  key={item.item_key}
                  to={item.path}
                  end={item.path === "/"}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon
                        className={cn(
                          "size-4 shrink-0 transition-colors",
                          isActive
                            ? "text-brand-cyan"
                            : "text-sidebar-foreground/60 group-hover:text-sidebar-foreground",
                        )}
                      />
                      {t(item.label_key)}
                    </>
                  )}
                </NavLink>
              );
            })}
      </nav>

      <div className="border-t border-sidebar-border px-5 py-3 text-xs text-sidebar-foreground/50">
        {t("app.panel_name")}
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 md:block">
      <SidebarContent />
    </aside>
  );
}
