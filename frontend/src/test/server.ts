/**
 * MSW mock API for vitest (node). Handlers live in ./handlers.ts so the browser mock mode can reuse
 * them.
 */
import { HttpResponse, type StrictResponse } from "msw";
import { setupServer } from "msw/node";
import type { Schemas } from "@/api/client";
import * as f from "./fixtures";
import { defaultHandlers } from "./handlers";

export { BASE, defaultHandlers, http } from "./handlers";

export const server = setupServer(...defaultHandlers);

/**
 * problem+json error response. Typed `StrictResponse<never>` so it can be returned from any
 * typed handler (openapi-msw unions only the documented bodies of that path).
 */
export function problemResponse(
  status: number,
  code: Schemas["ErrorCode"],
  extra: Partial<Schemas["Problem"]> = {},
): StrictResponse<never> {
  return HttpResponse.json(f.problem(status, code, extra), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  }) as unknown as StrictResponse<never>;
}

/** Simulated network failure (connection reset). */
export function networkError(): StrictResponse<never> {
  return HttpResponse.error() as unknown as StrictResponse<never>;
}
