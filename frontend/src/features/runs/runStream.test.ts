import { describe, expect, it } from "vitest";
import { buildMetricCharts } from "./metricGroups";
import { initialRunStreamState, MAX_LOG_LINES, runStreamReducer, type RunStreamState } from "./runStream";

const msg = (event: string, data: unknown, id: number | null = null) => ({
  type: "message" as const,
  msg: { event, data, id },
});

describe("runStreamReducer", () => {
  it("bootstraps from REST and merges live metric points without duplicates", () => {
    let s: RunStreamState = initialRunStreamState;
    s = runStreamReducer(
      s,
      msg("metrics", { kind: "metrics", step: 600, values: { loss: 0.8, lr: 1e-5 }, ts: "t" }, 3),
    );
    s = runStreamReducer(s, {
      type: "bootstrap",
      series: [{ key: "loss", steps: [200, 400, 600], values: [2, 1, 0.81] }],
      telemetry: [],
    });
    expect(s.metrics.loss?.steps).toEqual([200, 400, 600]);
    expect(s.metrics.loss?.values).toEqual([2, 1, 0.8]); // live value wins for the same step
    expect(s.metrics.lr?.steps).toEqual([600]);
    s = runStreamReducer(s, msg("metrics", { step: 800, values: { loss: Number.NaN } }));
    expect(s.metrics.loss?.values.at(-1)).toBeNull();
    expect(s.metricsVersion).toBe(3);
  });

  it("caps the log buffer and remembers the first byte offset", () => {
    let s = runStreamReducer(
      initialRunStreamState,
      msg("log", { kind: "log", byte_offset: 1000, lines: ["a", "b"] }),
    );
    s = runStreamReducer(
      s,
      msg("log", {
        kind: "log",
        byte_offset: 1004,
        lines: Array.from({ length: MAX_LOG_LINES }, (_, i) => `l${i}`),
      }),
    );
    expect(s.logs).toHaveLength(MAX_LOG_LINES);
    expect(s.logs.at(-1)).toBe(`l${MAX_LOG_LINES - 1}`);
    expect(s.firstLogOffset).toBe(1000);
  });

  it("tracks telemetry, progress, warnings and end", () => {
    let s = runStreamReducer(
      initialRunStreamState,
      msg("telemetry", {
        kind: "telemetry",
        gpu_id: "cuda0",
        ts: "2026-11-15T00:00:00Z",
        util_pct: 50,
        mem_used_mb: 1,
        mem_total_mb: 2,
        temperature_c: 40,
        power_w: 100,
      }),
    );
    s = runStreamReducer(s, msg("progress", { kind: "progress", step: 10, total_steps: 100, ts: "t" }));
    s = runStreamReducer(
      s,
      msg("warning", { kind: "warning", code: "nan_detected", message: "NaN", ts: "t" }, 5),
    );
    s = runStreamReducer(s, msg("end", { kind: "end", final_status: "failed" }));
    s = runStreamReducer(s, { type: "connection", status: "closed" });
    expect(s.telemetry).toHaveLength(1);
    expect(s.progress?.step).toBe(10);
    expect(s.notices[0]).toMatchObject({ kind: "warning", code: "nan_detected" });
    expect(s.ended).toBe("failed");
    expect(s.connection).toBe("closed");
    expect(runStreamReducer(s, { type: "reset" })).toBe(initialRunStreamState);
  });

  it("groups canonical metric keys into charts", () => {
    const charts = buildMetricCharts({
      loss: { steps: [1], values: [1] },
      l1_loss: { steps: [1], values: [1] },
      grad_norm: { steps: [1], values: [1] },
      lr: { steps: [1], values: [1] },
      samples_per_s: { steps: [1], values: [1] },
      update_s: { steps: [1], values: [1] },
      gpu_mem_gb: { steps: [1], values: [1] },
      epoch: { steps: [1], values: [1] },
      custom_metric: { steps: [1], values: [1] },
    });
    expect(charts.map((c) => c.id)).toEqual([
      "loss",
      "grad",
      "lr",
      "throughput",
      "timing",
      "memory",
      "other:custom_metric",
    ]);
    expect(charts[0]?.series.map((s) => s.label)).toEqual(["l1_loss", "loss"]);
  });
});
