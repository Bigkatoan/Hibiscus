/**
 * MSW handlers for every Station REST endpoint (§5.2), backed by a MockStation. Shared by vitest
 * (`server.use(...stationHandlers(sim))`) and the browser mock mode.
 */
import { http, HttpResponse, type HttpResponseResolver } from "msw";
import type { Arm, CameraConfig, RobotProfile, Settings } from "../api/types";
import * as fx from "./fixtures";
import { MockProblem, pairedLink, UNPAIRED, type MockStation } from "./sim";

function problem(status: number, code: string, params: Record<string, unknown> = {}) {
  return HttpResponse.json(
    { type: "about:blank", title: code, status, code, detail: null, request_id: "req_mock", params },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}

type Resolver = HttpResponseResolver<Record<string, string | readonly string[]>, never, never>;

/** Wraps a handler: MockProblem → problem+json, non-GET requests must carry X-Station: 1. */
function guard(fn: (args: Parameters<Resolver>[0]) => unknown): Resolver {
  return async (args) => {
    if (args.request.method !== "GET" && args.request.headers.get("X-Station") !== "1") {
      return problem(403, "forbidden_host");
    }
    try {
      const out = await fn(args);
      if (out instanceof Response) return out;
      if (out === undefined) return new HttpResponse(null, { status: 204 });
      return HttpResponse.json(out as Record<string, unknown>);
    } catch (e) {
      if (e instanceof MockProblem) return problem(e.status, e.code, e.params);
      throw e;
    }
  };
}

async function json<T>(req: Request): Promise<T> {
  const text = await req.text();
  return (text ? JSON.parse(text) : {}) as T;
}

export function stationHandlers(sim: MockStation, base = `${window.location.origin}/api/v1`) {
  const u = (p: string) => `${base}${p}`;
  return [
    http.get(
      u("/status"),
      guard(() => sim.status()),
    ),
    http.get(
      u("/settings"),
      guard(() => sim.settings),
    ),
    http.put(
      u("/settings"),
      guard(async ({ request }) => {
        const s = await json<Settings>(request);
        const th = s.thresholds;
        if (
          th.temp_critical_c > 67 ||
          th.temp_hot_c > th.temp_critical_c - 3 ||
          th.temp_warn_c > th.temp_hot_c - 5
        )
          throw new MockProblem(422, "validation_failed");
        sim.settings = s;
        return s;
      }),
    ),
    http.get(
      u("/ports"),
      guard(() => ({
        ports: fx.ports.map((p) => ({
          ...p,
          in_use_by:
            sim.status().robot?.connected && sim.profile?.follower.port === p.stable_path ? "follower" : null,
        })),
      })),
    ),
    http.post(
      u("/ports/detect"),
      guard(async ({ request }) => {
        const b = await json<{ method: string; ports_before?: string[] }>(request);
        if (b.method === "unplug" && !b.ports_before) return { ports_before: fx.ports.map((p) => p.device) };
        return { port: fx.ports[0] };
      }),
    ),
    http.get(
      u("/robots"),
      guard(() => ({ robots: sim.profiles, active: sim.activeId })),
    ),
    http.put(
      u("/robots/:id"),
      guard(async ({ request, params }) => {
        const p = await json<RobotProfile>(request);
        const id = String(params.id);
        if (sim.activeId === id && sim.moving) throw new MockProblem(409, "busy", { state: sim.state });
        sim.profiles = [...sim.profiles.filter((x) => x.id !== id), { ...p, id }];
        return { ...p, id };
      }),
    ),
    http.delete(
      u("/robots/:id"),
      guard(({ params }) => {
        sim.profiles = sim.profiles.filter((x) => x.id !== String(params.id));
        return undefined;
      }),
    ),
    http.post(
      u("/robots/:id/connect"),
      guard(({ params }) => sim.doConnect(String(params.id))),
    ),
    http.post(
      u("/robots/disconnect"),
      guard(() => sim.disconnect()),
    ),
    http.post(
      u("/robots/torque"),
      guard(async ({ request }) => {
        const b = await json<{ enabled: boolean }>(request);
        return sim.setTorque(b.enabled);
      }),
    ),
    http.get(
      u("/calibrations"),
      guard(() => ({ files: fx.calibrations })),
    ),
    http.post(
      u("/calibration/start"),
      guard(async ({ request }) => {
        const b = await json<{ arm: Arm; keep_existing?: boolean }>(request);
        return sim.calibrationStart(b.arm, Boolean(b.keep_existing));
      }),
    ),
    http.post(
      u("/calibration/step"),
      guard(async ({ request }) => {
        const b = await json<{ action: "set_home" | "finish_ranges" | "cancel" }>(request);
        return sim.calibrationStep(b.action);
      }),
    ),
    http.get(
      u("/cameras/discover"),
      guard(() => ({ cameras: fx.discovered })),
    ),
    http.post(
      u("/cameras/probe"),
      guard(async ({ request }) => {
        const c = await json<CameraConfig>(request);
        return {
          ok: true,
          measured_fps: c.fps >= 60 ? 31.2 : c.fps - 0.4,
          width: c.width,
          height: c.height,
          error: null,
          snapshot_jpeg_b64: null,
        };
      }),
    ),
    http.post(
      u("/sessions/teleop"),
      guard(async ({ request }) => sim.startSession("teleop", await json(request))),
    ),
    http.post(
      u("/sessions/record"),
      guard(async ({ request }) => sim.startSession("record", await json(request))),
    ),
    http.post(
      u("/sessions/replay"),
      guard(async ({ request }) => sim.startSession("replay", await json(request))),
    ),
    http.post(
      u("/sessions/run"),
      guard(async ({ request }) => sim.startSession("run", await json(request))),
    ),
    http.post(
      u("/sessions/current/control"),
      guard(async ({ request }) => {
        const b = await json<{ action: "next" | "rerecord" | "stop" }>(request);
        return sim.controlAction(b.action);
      }),
    ),
    http.post(
      u("/estop"),
      guard(() => sim.estop("user")),
    ),
    http.post(
      u("/estop/reset"),
      guard(() => sim.estopReset()),
    ),
    http.get(
      u("/sessions"),
      guard(() => ({ sessions: sim.sessionsHist })),
    ),
    http.get(
      u("/sessions/:id/telemetry"),
      guard(() => ({
        arm_motors: { follower: [...fx.MOTORS] },
        t: [],
        temp_c: {},
        voltage_v: {},
        current_a: {},
        load_pct: {},
        alerts: [],
      })),
    ),
    http.get(
      u("/datasets"),
      guard(() => ({ datasets: sim.datasets.map((d) => ({ ...d, episode_list: undefined })) })),
    ),
    http.get(
      u("/datasets/:name"),
      guard(({ params }) => {
        const d = sim.datasets.find((x) => x.name === String(params.name));
        if (!d) throw new MockProblem(404, "not_found");
        return d;
      }),
    ),
    http.delete(
      u("/datasets/:name"),
      guard(({ params }) => {
        if (sim.session?.s.dataset === String(params.name))
          throw new MockProblem(409, "busy", { state: sim.state });
        sim.datasets = sim.datasets.filter((x) => x.name !== String(params.name));
        return undefined;
      }),
    ),
    http.get(
      u("/datasets/:name/episodes/:i/telemetry"),
      guard(({ params }) => {
        const i = Number(params.i);
        const t = Array.from({ length: 61 }, (_, k) => k * 0.5);
        const temp = (base: number, slope: number) => t.map((x) => Math.round(base + slope * x));
        return {
          arm_motors: { follower: [...fx.MOTORS] },
          t,
          temp_c: {
            follower: Object.fromEntries(
              fx.MOTORS.map((m, k) => [m, temp(34 + k, m === "elbow_flex" ? 0.3 + i * 0.1 : 0.05)]),
            ),
          },
          voltage_v: {},
          current_a: {},
          load_pct: {},
          alerts:
            i >= 1
              ? [
                  {
                    t: 20,
                    level: "warn",
                    arm: "follower",
                    motor: "elbow_flex",
                    kind: "temperature",
                    value: 50,
                  },
                ]
              : [],
        };
      }),
    ),
    http.post(
      u("/datasets/:name/upload"),
      guard(({ params }) => {
        if (!sim.server.paired) throw new MockProblem(409, "not_paired");
        const d = sim.datasets.find((x) => x.name === String(params.name));
        if (!d) throw new MockProblem(404, "not_found");
        return sim.newJob("upload", d.name, d.size_bytes);
      }),
    ),
    http.get(
      u("/models"),
      guard(() => ({ models: sim.models, loaded: sim.loaded })),
    ),
    http.post(
      u("/models/import"),
      guard(() => sim.newJob("import", "upload", 200_000_000)),
    ),
    http.post(
      u("/models/pull"),
      guard(async ({ request }) => {
        if (!sim.server.paired) throw new MockProblem(409, "not_paired");
        const b = await json<{ server_model_id: string }>(request);
        return sim.newJob("pull", b.server_model_id, 1_050_000_000);
      }),
    ),
    http.get(
      u("/models/:key/compat"),
      guard(({ params }) => {
        const m = sim.models.find((x) => x.key === String(params.key));
        if (!m) throw new MockProblem(404, "not_found");
        const cams = sim.profile?.cameras ?? {};
        const checks = [
          { id: "state_dim", ok: true },
          { id: "action_dim", ok: true },
          ...Object.entries(m.input_features)
            .filter(([k]) => k.startsWith("observation.images."))
            .map(([k, f]) => {
              const name = k.replace("observation.images.", "");
              const c = cams[name];
              if (!c) return { id: `camera:${k}`, ok: false, code: "camera_missing" };
              const ok = f.shape[1] === c.height && f.shape[2] === c.width;
              return ok
                ? { id: `camera:${k}`, ok: true }
                : {
                    id: `camera:${k}`,
                    ok: false,
                    code: "shape_mismatch",
                    expected: f.shape,
                    actual: [3, c.height, c.width],
                    fix: { kind: "set_camera", camera: name, width: f.shape[2], height: f.shape[1] },
                  };
            }),
        ];
        return {
          ok: checks.every((c) => c.ok),
          policy_type: m.policy_type,
          device: "cpu",
          checks,
          warnings: [],
          defaults: { fps: m.fps ?? 30, task: m.task ?? "" },
        };
      }),
    ),
    http.post(
      u("/models/:key/load"),
      guard(({ params }) => sim.newJob("load", String(params.key), 100, "steps")),
    ),
    http.delete(
      u("/models/:key"),
      guard(({ params }) => {
        sim.models = sim.models.filter((m) => m.key !== String(params.key));
        return undefined;
      }),
    ),
    http.get(
      u("/jobs"),
      guard(() => ({ jobs: sim.jobs })),
    ),
    http.post(
      u("/jobs/:id/cancel"),
      guard(({ params }) => {
        const j = sim.jobs.find((x) => x.id === String(params.id));
        if (!j) throw new MockProblem(404, "not_found");
        j.status = "cancelled";
        return j;
      }),
    ),
    http.get(
      u("/server"),
      guard(() => sim.server),
    ),
    http.post(
      u("/server/pair"),
      guard(async ({ request }) => {
        const b = await json<{ url: string; token: string }>(request);
        if (!b.token.startsWith("hbp_")) throw new MockProblem(422, "validation_failed");
        sim.server = pairedLink(b.url.replace(/\/+$/, "").replace(/\/api\/v1$/, ""));
        return sim.server;
      }),
    ),
    http.delete(
      u("/server"),
      guard(() => {
        sim.server = { ...UNPAIRED };
        return undefined;
      }),
    ),
    http.get(
      u("/server/datasets"),
      guard(() => ({ datasets: fx.serverDatasets })),
    ),
    http.get(
      u("/server/models"),
      guard(() => ({ models: fx.serverModels })),
    ),
    http.get(
      u("/server/runs"),
      guard(() => ({ runs: fx.serverRuns })),
    ),
  ];
}
