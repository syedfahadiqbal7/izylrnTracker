/** School-admin auth endpoints (`/schools/auth/*`, `/schools/admins/me`). */
import { api, apiGet, apiPost } from "@/lib/api";
import { tokenStore } from "@/lib/tokenStore";
import type { SchoolAdmin, TokenPair } from "@/types/api";

export async function login(
  email: string,
  password: string,
): Promise<TokenPair> {
  const tokens = await apiPost<TokenPair>("/schools/auth/login", {
    email,
    password,
  });
  tokenStore.set(tokens);
  return tokens;
}

export async function fetchMe(): Promise<SchoolAdmin> {
  return apiGet<SchoolAdmin>("/schools/admins/me");
}

/** Revoke the current access + refresh tokens server-side, then clear locally. */
export async function logout(): Promise<void> {
  const refresh_token = tokenStore.getRefresh();
  try {
    if (refresh_token) {
      await api.delete("/schools/auth/logout", { data: { refresh_token } });
    }
  } catch {
    // Best-effort: even if revocation fails, drop the local session below.
  } finally {
    tokenStore.clear();
  }
}
