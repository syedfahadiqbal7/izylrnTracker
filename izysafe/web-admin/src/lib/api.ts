/**
 * Axios API client for the IzySafe backend.
 *
 * - Attaches the school-admin access token to every request.
 * - On a 401, transparently refreshes via POST /schools/auth/refresh (single-flight,
 *   so concurrent 401s share one refresh) and retries the original request once.
 * - Rotation: the refresh response's new access+refresh pair replaces the stored one.
 * - On refresh failure it clears the session and emits a forced-logout event.
 * - Normalizes the backend error envelope ({error, code, message}) into ApiClientError.
 */
import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from "axios";
import { API_BASE_URL } from "./env";
import { AUTH_LOGOUT_EVENT, emitForcedLogout, tokenStore } from "./tokenStore";
import {
  ApiClientError,
  type ApiError,
  type ApiSuccess,
  type ListMeta,
  type TokenPair,
} from "@/types/api";

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// Bare client for the refresh call itself — it must NOT go through the auth
// interceptor (no access token, no recursive refresh).
const refreshClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// --------------------------------------------------------------------------- //
// Request: attach bearer token
// --------------------------------------------------------------------------- //
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.getAccess();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

// --------------------------------------------------------------------------- //
// Response: refresh-on-401 (single-flight) + error normalization
// --------------------------------------------------------------------------- //
let refreshInFlight: Promise<string> | null = null;

async function runRefresh(): Promise<string> {
  const refreshToken = tokenStore.getRefresh();
  if (!refreshToken) throw new Error("no refresh token");
  const resp = await refreshClient.post<ApiSuccess<TokenPair>>(
    "/schools/auth/refresh",
    { refresh_token: refreshToken },
  );
  const tokens = resp.data.data;
  tokenStore.set(tokens);
  return tokens.access_token;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const original = error.config as RetriableConfig | undefined;

    // Attempt one refresh on a 401 (but never for the refresh/login calls).
    const isAuthPath =
      original?.url?.includes("/auth/refresh") ||
      original?.url?.includes("/auth/login");

    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !isAuthPath &&
      tokenStore.getRefresh()
    ) {
      original._retry = true;
      try {
        refreshInFlight ??= runRefresh().finally(() => {
          refreshInFlight = null;
        });
        const newAccess = await refreshInFlight;
        original.headers.set("Authorization", `Bearer ${newAccess}`);
        return api(original);
      } catch {
        tokenStore.clear();
        emitForcedLogout();
      }
    }

    return Promise.reject(toApiClientError(error));
  },
);

function toApiClientError(error: AxiosError<ApiError>): ApiClientError {
  const status = error.response?.status ?? 0;
  const body = error.response?.data;
  if (body && typeof body === "object" && "code" in body) {
    return new ApiClientError(status, body.code, body.message);
  }
  if (status === 0) {
    return new ApiClientError(0, "NETWORK_ERROR", "Could not reach the server");
  }
  return new ApiClientError(status, `HTTP_${status}`, error.message);
}

// --------------------------------------------------------------------------- //
// Typed helpers — unwrap the {data} / {data, meta} envelopes
// --------------------------------------------------------------------------- //
export async function apiGet<T>(
  url: string,
  config?: AxiosRequestConfig,
): Promise<T> {
  const resp = await api.get<ApiSuccess<T>>(url, config);
  return resp.data.data;
}

export async function apiGetList<T>(
  url: string,
  config?: AxiosRequestConfig,
): Promise<{ items: T; meta?: ListMeta }> {
  const resp = await api.get<ApiSuccess<T>>(url, config);
  return { items: resp.data.data, meta: resp.data.meta };
}

export async function apiPost<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const resp = await api.post<ApiSuccess<T>>(url, body, config);
  return resp.data.data;
}

export async function apiPut<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const resp = await api.put<ApiSuccess<T>>(url, body, config);
  return resp.data.data;
}

export async function apiPatch<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const resp = await api.patch<ApiSuccess<T>>(url, body, config);
  return resp.data.data;
}

export async function apiDelete<T>(
  url: string,
  config?: AxiosRequestConfig,
): Promise<T> {
  const resp = await api.delete<ApiSuccess<T>>(url, config);
  return resp.data.data;
}

export { AUTH_LOGOUT_EVENT };
