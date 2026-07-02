/**
 * Auth state for the admin panel.
 *
 * On mount, if a token is present we resolve the current admin via GET /admins/me
 * (this also validates the token). Login stores the JWT pair then loads the admin;
 * logout revokes server-side and clears local state. A forced-logout event from the
 * API client (refresh failure) drops the session so the app falls back to /login.
 */
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AUTH_LOGOUT_EVENT } from "@/lib/api";
import { tokenStore } from "@/lib/tokenStore";
import type { SchoolAdmin } from "@/types/api";
import * as authApi from "./authApi";

export interface AuthState {
  admin: SchoolAdmin | null;
  status: "loading" | "authenticated" | "unauthenticated";
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAdmin: () => Promise<void>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<SchoolAdmin | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");

  const loadAdmin = useCallback(async () => {
    const me = await authApi.fetchMe();
    setAdmin(me);
    setStatus("authenticated");
  }, []);

  // Bootstrap: validate any persisted token.
  useEffect(() => {
    if (!tokenStore.hasSession()) {
      setStatus("unauthenticated");
      return;
    }
    loadAdmin().catch(() => {
      tokenStore.clear();
      setAdmin(null);
      setStatus("unauthenticated");
    });
  }, [loadAdmin]);

  // React to forced logout from the API layer (refresh failed).
  useEffect(() => {
    const onForcedLogout = () => {
      setAdmin(null);
      setStatus("unauthenticated");
    };
    window.addEventListener(AUTH_LOGOUT_EVENT, onForcedLogout);
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, onForcedLogout);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      await authApi.login(email, password);
      await loadAdmin();
    },
    [loadAdmin],
  );

  const logout = useCallback(async () => {
    await authApi.logout();
    setAdmin(null);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo<AuthState>(
    () => ({ admin, status, login, logout, refreshAdmin: loadAdmin }),
    [admin, status, login, logout, loadAdmin],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
