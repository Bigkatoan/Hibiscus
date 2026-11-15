/**
 * Default MSW handlers generated from the OpenAPI `paths` type (openapi-msw): handler paths,
 * params, request bodies and response bodies are type-checked against api/openapi.yaml.
 * Shared by the vitest server (./server.ts) and the browser mock mode (src/mock/browser.ts).
 */
import { HttpResponse } from "msw";
import { createOpenApiHttp } from "openapi-msw";
import type { paths } from "@/api/generated/schema";
import * as f from "./fixtures";

export const BASE = `${window.location.origin}/api/v1`;
export const http = createOpenApiHttp<paths>({ baseUrl: BASE });

export const defaultHandlers = [
  http.get("/auth/me", () => HttpResponse.json(f.me)),
  http.get("/auth/config", () => HttpResponse.json(f.authConfig)),
  http.post("/auth/refresh", ({ response }) => response(204).empty()),
  http.post("/auth/logout", ({ response }) => response(204).empty()),
  http.get("/auth/sessions", () => HttpResponse.json({ items: f.sessions })),
  http.get("/auth/tokens", () => HttpResponse.json({ items: [f.apiToken] })),
  http.get("/users/me/secrets/hf-token", () =>
    HttpResponse.json({ present: false, hint: null, updated_at: null }),
  ),
  http.get("/users/me/notification-channels", () => HttpResponse.json({ items: [f.channel] })),
  http.get("/notifications", () =>
    HttpResponse.json({ items: [f.notification], next_cursor: null, unread_count: 1 }),
  ),
  http.get("/workspaces", () => HttpResponse.json({ items: [f.workspace, f.workspace2] })),
  http.get("/workspaces/{workspace_id}", () => HttpResponse.json(f.workspace)),
  http.get("/workspaces/{workspace_id}/members", () => HttpResponse.json({ items: f.members })),
  http.get("/workspaces/{workspace_id}/invites", () => HttpResponse.json({ items: [f.invite] })),
  http.get("/workspaces/{workspace_id}/usage", () => HttpResponse.json(f.usage)),
  http.get("/datasets", () => HttpResponse.json({ items: [f.dataset], next_cursor: null })),
  http.get("/datasets/{dataset_id}", () => HttpResponse.json(f.dataset)),
  http.get("/datasets/{dataset_id}/versions", () =>
    HttpResponse.json({ items: [f.versionSummary], next_cursor: null }),
  ),
  http.get("/dataset-versions/{version_id}", () => HttpResponse.json(f.datasetVersion)),
  http.get("/dataset-versions/{version_id}/validation", () => HttpResponse.json(f.validationReport)),
  http.get("/dataset-versions/{version_id}/preview", () => HttpResponse.json(f.preview)),
  http.get("/dataset-versions/{version_id}/episodes/{episode_index}", () => HttpResponse.json(f.episode)),
  http.get("/uploads", () => HttpResponse.json({ items: [], next_cursor: null })),
  http.get("/policies", () => HttpResponse.json({ lerobot_version: "0.7.1", items: f.policySummaries })),
  http.get("/policies/{policy_type}", () => HttpResponse.json(f.actPolicy)),
  http.get("/runs", () => HttpResponse.json({ items: [f.run, f.run2], next_cursor: null })),
  // Must precede /runs/{run_id} (a literal segment would otherwise match the template).
  http.get("/runs/compare", () =>
    HttpResponse.json({ runs: [f.run, f.run2], series: [f.metricSeries], config_diff: [] }),
  ),
  http.get("/runs/{run_id}", ({ params }) =>
    HttpResponse.json(params.run_id === f.IDS.run2 ? f.run2 : f.run),
  ),
  http.post("/runs/preflight", () => HttpResponse.json(f.preflightOk)),
  http.get("/runs/{run_id}/metrics", () => HttpResponse.json(f.metricSeries)),
  http.get("/runs/{run_id}/telemetry", () => HttpResponse.json({ items: [f.gpuSample] })),
  http.get("/runs/{run_id}/checkpoints", () => HttpResponse.json({ items: [f.checkpoint] })),
  http.get("/runs/{run_id}/events/history", () => HttpResponse.json({ items: [], last_seq: 0 })),
  http.get("/models", () => HttpResponse.json({ items: [f.model], next_cursor: null })),
  http.get("/models/{model_id}", () => HttpResponse.json(f.model)),
  http.get("/models/{model_id}/files", () => HttpResponse.json(f.bundleManifest)),
  http.get("/gpus", () => HttpResponse.json({ items: f.gpus })),
  http.get("/queue", () => HttpResponse.json({ items: [] })),
  http.get("/admin/users", () => HttpResponse.json({ items: [f.adminUser], next_cursor: null })),
  http.get("/admin/audit-events", () => HttpResponse.json({ items: [f.auditEvent], next_cursor: null })),
  http.get("/admin/workspaces/{workspace_id}/quotas", () => HttpResponse.json({ items: [f.quota] })),
  http.get("/admin/system", () => HttpResponse.json(f.system)),
];
