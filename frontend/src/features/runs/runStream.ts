/**
 * Live run state fed by REST bootstrap + SSE (streamRunEvents). The reducer is pure and unit
 * tested; `useRunStream` wires it to openSse and the query cache.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useReducer } from "react";
import { api, apiUrl, unwrap, type Schemas } from "@/api/client";
import { qk } from "@/api/hooks/keys";
import { openSse, type EventSourceFactory, type SseMessage, type SseStatus } from "@/api/sse";
import { appendPoint } from "@/components/charts/series";
import { isRecord } from "@/lib/utils";

type S = Schemas;

export const RUN_EVENTS = [
  "status",
  "metrics",
  "checkpoint",
  "warning",
  "error",
  "model",
  "eval",
  "progress",
  "log",
  "telemetry",
  "heartbeat",
  "end",
] as const;

export const MAX_LOG_LINES = 5000;
export const MAX_TELEMETRY = 2000;

export interface SeriesBuf {
  steps: number[];
  values: (number | null)[];
}

export interface RunStreamState {
  metrics: Record<string, SeriesBuf>;
  /** Bumped on every metrics mutation so memoised charts re-render. */
  metricsVersion: number;
  logs: string[];
  firstLogOffset: number | null;
  telemetry: S["GpuSample"][];
  notices: {
    kind: "warning" | "error";
    code: string;
    message: string;
    ts: string;
    params?: Record<string, unknown>;
  }[];
  progress: S["ProgressEvent"] | null;
  connection: SseStatus | "idle";
  ended: S["RunStatus"] | null;
}

export const initialRunStreamState: RunStreamState = {
  metrics: {},
  metricsVersion: 0,
  logs: [],
  firstLogOffset: null,
  telemetry: [],
  notices: [],
  progress: null,
  connection: "idle",
  ended: null,
};

export type RunStreamAction =
  | { type: "bootstrap"; series: S["MetricSeries"][]; telemetry: S["GpuSample"][] }
  | { type: "message"; msg: SseMessage }
  | { type: "connection"; status: SseStatus }
  | { type: "reset" };

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function runStreamReducer(state: RunStreamState, action: RunStreamAction): RunStreamState {
  switch (action.type) {
    case "reset":
      return initialRunStreamState;
    case "connection":
      return { ...state, connection: action.status };
    case "bootstrap": {
      const metrics: Record<string, SeriesBuf> = { ...state.metrics };
      for (const s of action.series) {
        const buf: SeriesBuf = { steps: [...s.steps], values: [...s.values] };
        // Merge any live points that arrived before the REST response.
        const live = state.metrics[s.key];
        if (live)
          live.steps.forEach((st, i) => {
            appendPoint(buf, st, live.values[i] ?? null);
          });
        metrics[s.key] = buf;
      }
      const telemetry = [...action.telemetry, ...state.telemetry].slice(-MAX_TELEMETRY);
      return { ...state, metrics, telemetry, metricsVersion: state.metricsVersion + 1 };
    }
    case "message": {
      const { event, data } = action.msg;
      const d = isRecord(data) ? data : {};
      switch (event) {
        case "metrics": {
          const step = num(d.step);
          const values = isRecord(d.values) ? d.values : {};
          if (step === null) return state;
          const metrics = { ...state.metrics };
          for (const [k, v] of Object.entries(values)) {
            const prev = metrics[k];
            const buf: SeriesBuf = prev
              ? { steps: [...prev.steps], values: [...prev.values] }
              : { steps: [], values: [] };
            appendPoint(buf, step, num(v));
            metrics[k] = buf;
          }
          return { ...state, metrics, metricsVersion: state.metricsVersion + 1 };
        }
        case "log": {
          const lines = Array.isArray(d.lines)
            ? d.lines.filter((l): l is string => typeof l === "string")
            : [];
          const logs = [...state.logs, ...lines].slice(-MAX_LOG_LINES);
          const offset = num(d.byte_offset);
          return { ...state, logs, firstLogOffset: state.firstLogOffset ?? offset };
        }
        case "telemetry": {
          const sample = d as unknown as S["GpuSample"];
          if (typeof sample.ts !== "string") return state;
          return { ...state, telemetry: [...state.telemetry, sample].slice(-MAX_TELEMETRY) };
        }
        case "progress":
          return { ...state, progress: d as unknown as S["ProgressEvent"] };
        case "warning":
        case "error":
          return {
            ...state,
            notices: [
              ...state.notices,
              {
                kind: event,
                code: typeof d.code === "string" ? d.code : "unknown",
                message: typeof d.message === "string" ? d.message : "",
                ts: typeof d.ts === "string" ? d.ts : new Date().toISOString(),
                ...(isRecord(d.params) ? { params: d.params } : {}),
              },
            ].slice(-100),
          };
        case "end":
          return {
            ...state,
            ended: (typeof d.final_status === "string" ? d.final_status : "succeeded") as S["RunStatus"],
          };
        default:
          return state;
      }
    }
    default:
      return state;
  }
}

/** Keys that should be patched into / invalidated in the query cache for an SSE message. */
export function applyRunMessageToCache(
  qc: ReturnType<typeof useQueryClient>,
  runId: string,
  msg: SseMessage,
): void {
  const d = isRecord(msg.data) ? msg.data : {};
  switch (msg.event) {
    case "progress":
      qc.setQueryData<S["Run"]>(qk.run(runId), (run) =>
        run
          ? {
              ...run,
              progress: {
                ...run.progress,
                current_step: num(d.step) ?? run.progress.current_step,
                total_steps: num(d.total_steps) ?? run.progress.total_steps,
                steps_per_s: num(d.steps_per_s),
                eta_s: num(d.eta_s),
              },
            }
          : run,
      );
      break;
    case "status":
      qc.setQueryData<S["Run"]>(qk.run(runId), (run) =>
        run && typeof d.to === "string" ? { ...run, status: d.to as S["RunStatus"] } : run,
      );
      void qc.invalidateQueries({ queryKey: qk.run(runId) });
      break;
    case "checkpoint":
      void qc.invalidateQueries({ queryKey: qk.runCheckpoints(runId) });
      void qc.invalidateQueries({ queryKey: qk.run(runId) });
      break;
    case "model":
    case "eval":
    case "end":
    case "error":
      void qc.invalidateQueries({ queryKey: qk.run(runId) });
      void qc.invalidateQueries({ queryKey: qk.runCheckpoints(runId) });
      break;
    default:
      break;
  }
}

export function useRunStream(runId: string, live: boolean, factory?: EventSourceFactory): RunStreamState {
  const qc = useQueryClient();
  const [state, dispatch] = useReducer(runStreamReducer, initialRunStreamState);

  useEffect(() => {
    dispatch({ type: "reset" });
    const life = { cancelled: false };
    let sub: { close: () => void } | null = null;
    void (async () => {
      // 1) remember where the persisted stream is, 2) load history via REST, 3) go live after it.
      let lastSeq = 0;
      if (live) {
        try {
          const h = await unwrap(
            api.GET("/runs/{run_id}/events/history", {
              params: { path: { run_id: runId }, query: { limit: 1, types: ["status"] } },
            }),
          );
          lastSeq = h.last_seq;
        } catch {
          lastSeq = 0;
        }
      }
      const [metrics, telemetry] = await Promise.allSettled([
        unwrap(
          api.GET("/runs/{run_id}/metrics", {
            params: { path: { run_id: runId }, query: { max_points: 2000 } },
          }),
        ),
        unwrap(
          api.GET("/runs/{run_id}/telemetry", {
            params: { path: { run_id: runId }, query: { max_points: 1000 } },
          }),
        ),
      ]);
      if (life.cancelled) return;
      dispatch({
        type: "bootstrap",
        series:
          metrics.status === "fulfilled" && typeof metrics.value !== "string" ? metrics.value.series : [],
        telemetry: telemetry.status === "fulfilled" ? telemetry.value.items : [],
      });
      if (!live || (!("EventSource" in globalThis) && !factory)) return;
      sub = openSse({
        url: (seq) => apiUrl(`/runs/${runId}/events`, { after_seq: seq ?? lastSeq }),
        events: RUN_EVENTS,
        initialSeq: lastSeq,
        onMessage: (msg) => {
          dispatch({ type: "message", msg });
          applyRunMessageToCache(qc, runId, msg);
        },
        onStatus: (status) => {
          dispatch({ type: "connection", status });
        },
        ...(factory ? { factory } : {}),
      });
    })();
    return () => {
      life.cancelled = true;
      sub?.close();
    };
  }, [runId, live, qc, factory]);

  return state;
}
