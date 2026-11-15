/**
 * Browser mock mode (`vite build --mode mock` / `vite --mode mock`): the SPA runs against the same
 * typed MSW handlers as the vitest suite, so every screen can be opened without a backend (UI
 * review, screenshots). Never part of the production bundle: main.tsx only imports this module
 * when `import.meta.env.VITE_HIBISCUS_MOCK === "1"`.
 *
 * Query switches (remembered for the tab in sessionStorage):
 *   ?mock_auth=0   signed out (login page)        ?mock_lang=en  profile locale (default vi)
 *   ?mock_empty=1  empty lists (empty states)
 */
import { http as rawHttp, HttpResponse } from "msw";
import { setupWorker } from "msw/browser";
import type { Schemas } from "@/api/client";
import * as f from "@/test/fixtures";
import { BASE, defaultHandlers, http } from "@/test/handlers";
import { createMockEventSource } from "./mockEventSource";

function flag(name: string, fallback: string): string {
  const q = new URLSearchParams(window.location.search).get(name);
  try {
    if (q !== null) window.sessionStorage.setItem(name, q);
    return window.sessionStorage.getItem(name) ?? fallback;
  } catch {
    return q ?? fallback;
  }
}

const RUN_IDS = {
  queued: "66666666-6666-4666-8666-000000000001",
  failed: "66666666-6666-4666-8666-000000000002",
} as const;

const runQueued: Schemas["Run"] = {
  ...f.run,
  id: RUN_IDS.queued,
  number: 8,
  name: "diffusion-sorting",
  policy_type: "diffusion",
  status: "queued",
  queue_position: 2,
  gpu_id: null,
  progress: { ...f.run.progress, current_step: 0, steps_per_s: null, eta_s: null },
  allowed_actions: ["cancel", "edit"],
};

const runFailed: Schemas["Run"] = {
  ...f.run2,
  id: RUN_IDS.failed,
  number: 5,
  name: "pi0-towel-fold",
  policy_type: "pi0",
  status: "failed",
  error_code: "oom",
  error_message: "CUDA out of memory. Tried to allocate 2.00 GiB (GPU 0; 11.76 GiB total capacity)",
  progress: { ...f.run2.progress, current_step: 1830 },
  allowed_actions: ["clone"],
};

const RUNS: Record<string, Schemas["Run"]> = {
  [f.IDS.run]: f.run,
  [f.IDS.run2]: f.run2,
  [RUN_IDS.queued]: runQueued,
  [RUN_IDS.failed]: runFailed,
};

const MOCK_LOG = Array.from(
  { length: 50 },
  (_, i) =>
    `step:${(i + 1) * 200} smpl:${(i + 1) * 1600} loss:${(0.25 + 2 * Math.exp(-(i + 1) / 8)).toFixed(3)}`,
).join("\n");

const dataset2: Schemas["Dataset"] = {
  ...f.dataset,
  id: "33333333-3333-4333-8333-000000000002",
  name: "Gắp đặt khối gỗ – tay trái",
  slug: "gap-dat-khoi-go",
  description: "Camera cổ tay + camera trên cao, 48 tập",
};

export async function startMockWorker(): Promise<void> {
  const signedOut = flag("mock_auth", "1") === "0";
  const lang = flag("mock_lang", "vi") === "en" ? "en" : "vi";
  const empty = flag("mock_empty", "0") === "1";
  const me: Schemas["Me"] = { ...f.me, user: { ...f.me.user, locale: lang, display_name: "Nguyễn Thị Ánh" } };

  const worker = setupWorker(
    http.get("/auth/me", () =>
      signedOut
        ? HttpResponse.json(f.problem(401, "unauthenticated"), {
            status: 401,
            headers: { "Content-Type": "application/problem+json" },
          })
        : HttpResponse.json(me),
    ),
    http.post("/auth/refresh", ({ response }) =>
      signedOut ? response(401).json(f.problem(401, "unauthenticated")) : response(204).empty(),
    ),
    http.get("/datasets", () =>
      HttpResponse.json({ items: empty ? [] : [f.dataset, dataset2], next_cursor: null }),
    ),
    http.get("/runs", () =>
      HttpResponse.json({ items: empty ? [] : Object.values(RUNS), next_cursor: null }),
    ),
    http.get("/runs/{run_id}", ({ params }) => HttpResponse.json(RUNS[params.run_id] ?? f.run)),
    http.get("/models", () => HttpResponse.json({ items: empty ? [] : [f.model], next_cursor: null })),
    // Stored log (Log tab of finished runs, "Load full log", Range requests).
    rawHttp.get(
      `${BASE}/runs/:runId/logs`,
      () => new HttpResponse(MOCK_LOG, { headers: { "Content-Type": "text/plain" } }),
    ),
    ...defaultHandlers,
  );
  await worker.start({ onUnhandledRequest: "bypass", quiet: true });
  // MSW 2.7 cannot intercept EventSource: give the live views an in-page stream instead.
  globalThis.EventSource = createMockEventSource({ runs: RUNS }) as unknown as typeof EventSource;
}
