import { NavLink } from "react-router-dom";
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
      <div className="flex h-16 items-center gap-2.5 border-b border-sidebar-border px-5">
        <img
          src="/izylrn-icon.png"
          alt="izyLrn"
          className="size-8 shrink-0 object-contain"
        />
        <div className="leading-tight">
          <span className="text-lg font-extrabold tracking-tight">
            izy<span className="text-brand-cyan">Lrn</span>
          </span>
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {items.map(({ label, to, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
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
                    "size-4 transition-colors",
                    isActive
                      ? "text-brand-cyan"
                      : "text-sidebar-foreground/60 group-hover:text-sidebar-foreground",
                  )}
                />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-sidebar-border px-5 py-3 text-xs text-sidebar-foreground/50">
        School Admin Panel
      </div>
    </aside>
  );
}
