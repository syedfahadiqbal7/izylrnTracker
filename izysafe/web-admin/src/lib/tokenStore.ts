/**
 * Persists the school-admin JWT pair in localStorage.
 *
 * Access token (24h) rides on every request; the refresh token (30d) is used
 * only by the refresh interceptor. Rotation replaces both on each refresh.
 */
import type { TokenPair } from "@/types/api";

const ACCESS_KEY = "izysafe.access_token";
const REFRESH_KEY = "izysafe.refresh_token";

export const tokenStore = {
  getAccess(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  },
  getRefresh(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(tokens: Pick<TokenPair, "access_token" | "refresh_token">): void {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  },
  clear(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  hasSession(): boolean {
    return Boolean(localStorage.getItem(ACCESS_KEY));
  },
};

/** Broadcast a forced logout so the AuthProvider can redirect to /login. */
export const AUTH_LOGOUT_EVENT = "izysafe:auth:logout";

export function emitForcedLogout(): void {
  window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
}
