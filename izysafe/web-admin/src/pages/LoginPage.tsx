import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/useAuth";
import { useT } from "@/lib/i18n/I18nProvider";
import { ApiClientError } from "@/types/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginPage() {
  const { status, login } = useAuth();
  const t = useT();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated") {
    return <Navigate to={from} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(
          err.code === "INVALID_CREDENTIALS" || err.status === 401
            ? t("login.incorrect", "Incorrect email or password.")
            : err.message,
        );
      } else {
        setError(t("common.error_generic", "Something went wrong. Please try again."));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-muted/40 p-4">
      {/* Brand gradient wash */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-brand-gradient opacity-90" />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent to-background" />

      <Card className="relative w-full max-w-sm shadow-xl">
        <CardHeader className="space-y-3 text-center">
          <img
            src="/izylrn-icon.png"
            alt="izyLrn"
            className="mx-auto size-14 object-contain"
          />
          <CardTitle className="text-2xl font-extrabold tracking-tight">
            izy<span className="text-brand-gradient">Lrn</span>
          </CardTitle>
          <CardDescription>
            {t("login.subtitle", "School Admin — sign in to your dashboard")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">{t("common.email", "Email")}</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@school.edu"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">{t("common.password", "Password")}</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && (
              <p className="text-sm font-medium text-destructive">{error}</p>
            )}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? t("login.signing_in", "Signing in…") : t("login.sign_in", "Sign in")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
