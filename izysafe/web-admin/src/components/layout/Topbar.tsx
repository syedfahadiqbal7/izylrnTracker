import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut, Menu, UserRound } from "lucide-react";
import { useAuth } from "@/auth/useAuth";
import { useT } from "@/lib/i18n/I18nProvider";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { SidebarContent } from "./Sidebar";

export function Topbar() {
  const { admin, logout } = useAuth();
  const t = useT();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const onLogout = async () => {
    setSigningOut(true);
    try {
      await logout();
      navigate("/login", { replace: true });
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4 sm:px-6">
      <div className="flex items-center gap-2">
        {/* Mobile menu */}
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden">
              <Menu className="size-5" />
              <span className="sr-only">Open menu</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="p-0">
            <SidebarContent onNavigate={() => setMenuOpen(false)} />
          </SheetContent>
        </Sheet>
        <span className="text-sm text-muted-foreground">
          {admin?.role === "admin" ? t("app.administrator") : t("app.staff")}
        </span>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <LanguageSwitcher />
        <div className="flex items-center gap-2 text-sm">
          <UserRound className="size-4 text-muted-foreground" />
          <span className="hidden max-w-[10rem] truncate font-medium sm:inline">
            {admin?.name ?? admin?.email}
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onLogout}
          disabled={signingOut}
        >
          <LogOut className="size-4" />
          <span className="hidden sm:inline">
            {signingOut ? t("app.signing_out") : t("app.sign_out")}
          </span>
        </Button>
      </div>
    </header>
  );
}
