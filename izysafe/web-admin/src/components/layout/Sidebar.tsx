import { NavLink } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/auth/useAuth";
import { NAV_ITEMS } from "./nav";

export function Sidebar() {
  const { admin } = useAuth();
  const items = NAV_ITEMS.filter(
    (item) => !item.adminOnly || admin?.role === "admin",
  );

  return (
    <aside className="hidden w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground md:flex">
      <div className="flex h-14 items-center gap-2 border-b border-sidebar-border px-5">
        <ShieldCheck className="size-6 text-primary" />
        <span className="text-base font-semibold tracking-tight">IzySafe</span>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {items.map(({ label, to, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
              )
            }
          >
            <Icon className="size-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-sidebar-border px-5 py-3 text-xs text-sidebar-foreground/50">
        School Admin Panel
      </div>
    </aside>
  );
}
