/**
 * Map API errors to i18n keys. UI never shows `detail` text (English, server-side); it localises
 * from the stable `code` (ADR-0007 follow-ups).
 */
import type { TFunction } from "i18next";
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { ApiError } from "@/api/client";

export interface ErrorKey {
  key: string;
  params: Record<string, unknown>;
}

export function errorKey(error: unknown): ErrorKey {
  if (error instanceof ApiError) {
    const params: Record<string, unknown> = { ...(error.problem?.params ?? {}) };
    if (error.retryAfterS !== undefined) params.retry_after_s = error.retryAfterS;
    return { key: `errors.${error.code}`, params };
  }
  return { key: "errors.unknown_error", params: {} };
}

/** FieldError.loc is e.g. ["body", "email"] or ["body","config","policy","chunk_size"]. */
export function fieldPath(loc: readonly (string | number)[]): string {
  const parts = loc[0] === "body" || loc[0] === "query" || loc[0] === "path" ? loc.slice(1) : loc;
  return parts.map(String).join(".");
}

/**
 * Push 422 field errors into react-hook-form. Returns true when at least one field matched;
 * callers still show a form-level alert otherwise.
 */
export function applyFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  known: readonly string[],
  translate: TFunction,
): boolean {
  if (!(error instanceof ApiError)) return false;
  const errs = error.problem?.errors ?? [];
  let matched = false;
  for (const fe of errs) {
    const path = fieldPath(fe.loc);
    if (known.includes(path)) {
      setError(path as Path<T>, {
        type: "server",
        message: translate(`field_errors.${fe.code}`, { defaultValue: translate(`errors.${error.code}`) }),
      });
      matched = true;
    }
  }
  return matched;
}
