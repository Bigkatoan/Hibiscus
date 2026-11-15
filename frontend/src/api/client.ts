/**
 * Thin hand-written layer over the generated client (`src/api/generated/schema.d.ts`, never edited).
 *
 * Responsibilities (ADR-0006 / ADR-0007):
 *  - same-origin cookie session; `X-CSRF-Token` (double-submit of the `hb_csrf` cookie) on every
 *    unsafe method;
 *  - on 401 `token_expired`: single-flight `POST /auth/refresh`, then retry the request once;
 *  - problem+json -> `ApiError` (UI maps `code` to an i18n key, never `detail`).
 */
import createClient from "openapi-fetch";
import type { components, paths } from "./generated/schema";

export type Schemas = components["schemas"];
export type Problem = Schemas["Problem"];
export type ErrorCode = Schemas["ErrorCode"];

export const API_PREFIX = "/api/v1";
export const CSRF_COOKIE = "hb_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function apiBaseUrl(): string {
  return `${window.location.origin}${API_PREFIX}`;
}

/** Absolute URL for an API path (for <video src>, <a href download>, EventSource). */
export function apiUrl(path: string, query?: Record<string, string | number | boolean | undefined>): string {
  const url = new URL(`${API_PREFIX}${path}`, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

export function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const c = part.trim();
    if (c.startsWith(prefix)) return decodeURIComponent(c.slice(prefix.length));
  }
  return null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode | "network_error" | "unknown_error";
  readonly problem: Problem | null;

  constructor(status: number, problem: Problem | null, fallbackCode?: "network_error" | "unknown_error") {
    super(problem?.detail ?? problem?.title ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
    this.code = problem?.code ?? fallbackCode ?? "unknown_error";
  }

  get requestId(): string | undefined {
    return this.problem?.request_id;
  }

  get retryAfterS(): number | undefined {
    return this.problem?.retry_after_s;
  }
}

export function isProblem(value: unknown): value is Problem {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.code === "string" && typeof v.status === "number" && typeof v.title === "string";
}

export async function problemFromResponse(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.clone().json();
  } catch {
    body = null;
  }
  return new ApiError(response.status, isProblem(body) ? body : null);
}

// ---------------------------------------------------------------------------------------------
// Session refresh (single flight) + unauthenticated hook
// ---------------------------------------------------------------------------------------------

type UnauthenticatedListener = (code: string) => void;
const unauthenticatedListeners = new Set<UnauthenticatedListener>();

/** Called when a request is unauthenticated and refresh did not help (session gone). */
export function onUnauthenticated(listener: UnauthenticatedListener): () => void {
  unauthenticatedListeners.add(listener);
  return () => unauthenticatedListeners.delete(listener);
}

function emitUnauthenticated(code: string): void {
  for (const l of unauthenticatedListeners) l(code);
}

let refreshInFlight: Promise<boolean> | null = null;

function csrfHeaders(): Record<string, string> {
  const token = readCookie(CSRF_COOKIE);
  return token ? { [CSRF_HEADER]: token } : {};
}

/** POST /auth/refresh (operationId refreshSession). Concurrent callers share one request. */
export function refreshSession(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      const res = await globalThis.fetch(`${apiBaseUrl()}/auth/refresh`, {
        method: "POST",
        credentials: "same-origin",
        headers: csrfHeaders(),
      });
      return res.status === 204 || res.ok;
    } catch {
      return false;
    } finally {
      // Callers that joined this flight already hold the promise; the next expiry refreshes anew.
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

const NO_REFRESH_PATHS = ["/auth/refresh", "/auth/login", "/auth/login/2fa", "/auth/logout"];

function withCsrf(request: Request): Request {
  if (!UNSAFE_METHODS.has(request.method.toUpperCase())) return request;
  const token = readCookie(CSRF_COOKIE);
  if (!token) return request;
  const headers = new Headers(request.headers);
  headers.set(CSRF_HEADER, token);
  return new Request(request, { headers });
}

async function problemCode(response: Response): Promise<string | null> {
  if (response.status !== 401) return null;
  try {
    const body: unknown = await response.clone().json();
    return isProblem(body) ? body.code : null;
  } catch {
    return null;
  }
}

/**
 * fetch used by the generated client and by raw callers (logs, uploads fallback).
 * The request body must be replayable: we clone before the first attempt.
 */
export async function authFetch(input: Request): Promise<Response> {
  const path = new URL(input.url).pathname.replace(API_PREFIX, "");
  const retryCopy = input.clone();
  const first = await globalThis.fetch(withCsrf(input));
  if (first.status !== 401 || NO_REFRESH_PATHS.includes(path)) return first;

  const code = await problemCode(first);
  if (code !== "token_expired") {
    if (code && code !== "invalid_credentials" && code !== "mfa_invalid_code") emitUnauthenticated(code);
    return first;
  }
  const refreshed = await refreshSession();
  if (!refreshed) {
    emitUnauthenticated("session_expired");
    return first;
  }
  const second = await globalThis.fetch(withCsrf(retryCopy));
  if (second.status === 401) emitUnauthenticated((await problemCode(second)) ?? "unauthenticated");
  return second;
}

/** Generated, fully typed client. Same origin as the SPA (no CORS in production, ADR-0007). */
export const api = createClient<paths>({
  baseUrl: apiBaseUrl(),
  fetch: (req) => authFetch(req),
  credentials: "same-origin",
  querySerializer: { array: { style: "form", explode: false } },
});

interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Await a generated-client call, returning `data` or throwing `ApiError`. */
export async function unwrap<T>(call: Promise<ApiResult<T>>): Promise<T> {
  let result: ApiResult<T>;
  try {
    result = await call;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, null, "network_error");
  }
  if (!result.response.ok) {
    throw new ApiError(result.response.status, isProblem(result.error) ? result.error : null);
  }
  return result.data as T;
}

/** Random Idempotency-Key (contract: 8..64 chars of [A-Za-z0-9_.:-]). */
export function newIdempotencyKey(): string {
  return `fe-${crypto.randomUUID()}`;
}
