/**
 * API contract types mirroring the IzySafe backend envelopes (CLAUDE.md §6).
 *
 *   Success (single): { "data": { ... } }
 *   Success (list):   { "data": [ ... ], "meta": { "total": N, ... } }
 *   Error:            { "error": true, "code": "ERROR_CODE", "message": "..." }
 */

export interface ApiSuccess<T> {
  data: T;
  meta?: ListMeta;
}

export interface ListMeta {
  total: number;
  limit: number;
  offset: number;
}

export interface ApiError {
  error: true;
  code: string;
  message: string;
}

/** Thrown by the API client on any non-2xx response, carrying the backend code. */
export class ApiClientError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
  }
}

// --------------------------------------------------------------------------- //
// Auth
// --------------------------------------------------------------------------- //
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type AdminRole = "admin" | "staff";

export interface SchoolAdmin {
  id: string;
  school_id: string;
  email: string;
  name: string | null;
  role: AdminRole;
  active: boolean;
  last_login_at: string | null;
  created_at: string;
}
