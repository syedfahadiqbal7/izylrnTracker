import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut, UserRound } from "lucide-react";
import { useAuth } from "@/auth/useAuth";
import { Button } from "@/components/ui/button";

export function Topbar() {
  const { admin, logout } = useAuth();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);

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
    <header className="flex h-14 items-center justify-between border-b bg-background px-6">
      <div className="text-sm text-muted-foreground">
        {admin?.role === "admin" ? "Administrator" : "Staff"}
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm">
          <UserRound className="size-4 text-muted-foreground" />
          <span className="font-medium">{admin?.name ?? admin?.email}</span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onLogout}
          disabled={signingOut}
        >
          <LogOut className="size-4" />
          {signingOut ? "Signing out…" : "Sign out"}
        </Button>
      </div>
    </header>
  );
}
