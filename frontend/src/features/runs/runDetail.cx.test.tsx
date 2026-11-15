/**
 * Run detail regressions from the phase-4 CX / e2e review: metrics honesty box (CX-01), failed-run
 * recovery buttons (CX-06), no stale progress fields on finished runs (CX-11), chart ticks for tiny
 * learning rates and single-point series (CX-05, QC-e2e-11), finished-run logs (QC-e2e-11).
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http as rawHttp, HttpResponse } from "msw";
import uPlot from "uplot";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { axisValues, showPoints } from "@/components/charts/LineChart";
import * as f from "@/test/fixtures";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderApp } from "@/test/render";
import { BASE, http, server } from "@/test/server";
import { applyCloneAdjust, cloneHref, recoveryActions } from "./recovery";

interface RecordedPlot {
  opts: {
    series: { label?: string; points?: { show?: unknown } }[];
    axes: { values?: (u: unknown, splits: number[]) => string[] }[];
  };
  el: HTMLElement;
}
const plots = () => (uPlot as unknown as { instances: RecordedPlot[] }).instances;

describe("run detail CX fixes", () => {
  const original = globalThis.EventSource;
  beforeEach(() => {
    FakeEventSource.reset();
    globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
  });
  afterEach(() => {
    globalThis.EventSource = original;
  });

  it("metrics tab always shows the non-dismissable 'low loss is not robot success' box", async () => {
    renderApp(`/w/robot-lab/runs/${f.IDS.run}`);
    const box = await screen.findByTestId("metrics-honesty");
    expect(box).toHaveTextContent("How to read these numbers");
    expect(box).toHaveTextContent(/low loss does NOT mean the robot will do the task/);
    expect(within(box).queryByRole("button")).toBeNull();
  });

  it("finished run: MAE in the summary with the disclaimer, no stale ETA/next checkpoint", async () => {
    renderApp(`/w/robot-lab/runs/${f.IDS.run2}`);
    expect(await screen.findByTestId("mae-disclaimer")).toHaveTextContent(
      "not a success rate on the real robot",
    );
    expect(screen.getByText("Held-out MAE")).toBeInTheDocument();
    expect(screen.queryByText("Next checkpoint")).toBeNull();
    expect(screen.queryByText("Time left")).toBeNull();
    expect(screen.queryByText("Speed")).toBeNull();
    expect(screen.getByText("Last checkpoint")).toBeInTheDocument();
  });

  it("running run keeps speed / ETA / next checkpoint", async () => {
    renderApp(`/w/robot-lab/runs/${f.IDS.run}`);
    expect(await screen.findByText("Next checkpoint")).toBeInTheDocument();
    expect(screen.getByText("Time left")).toBeInTheDocument();
  });

  it("failed OOM run offers 'clone with half batch' and 'clone on the P40'; the wizard applies it", async () => {
    server.use(
      http.get("/runs/{run_id}", () =>
        HttpResponse.json({
          ...f.run2,
          status: "failed",
          error_code: "oom",
          gpu_id: "cuda0",
          error_message: "CUDA out of memory",
          allowed_actions: ["clone"],
          config: { ...f.run2.config, train: { batch_size: 16 } },
        }),
      ),
    );
    const { router } = renderApp(`/w/robot-lab/runs/${f.IDS.run2}`);
    const actions = await screen.findByTestId("recovery-actions");
    expect(await within(actions).findByRole("button", { name: /Clone on Tesla P40/ })).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(within(actions).getByRole("button", { name: /Clone with half the batch size/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/w/robot-lab/runs/new");
    });
    expect(router.state.location.search).toBe(`?clone=${f.IDS.run2}&adjust=half_batch`);
    expect(await screen.findByTestId("clone-adjusted")).toHaveTextContent("from 16 to 8");
  });

  it("failed worker_lost run with resume allowed offers 'Resume from checkpoint'", async () => {
    server.use(
      http.get("/runs/{run_id}", () =>
        HttpResponse.json({
          ...f.run2,
          status: "failed",
          error_code: "worker_lost",
          allowed_actions: ["clone", "resume"],
        }),
      ),
    );
    renderApp(`/w/robot-lab/runs/${f.IDS.run2}`);
    const actions = await screen.findByTestId("recovery-actions");
    expect(within(actions).getByRole("button", { name: "Resume from checkpoint" })).toBeInTheDocument();
  });

  it("finished run's Log tab loads the stored log without clicking", async () => {
    server.use(
      rawHttp.get(
        `${BASE}/runs/:runId/logs`,
        () => new HttpResponse("step:200 loss:0.9\nstep:400 loss:0.5\n"),
      ),
    );
    renderApp(`/w/robot-lab/runs/${f.IDS.run2}?tab=logs`);
    expect(await screen.findByText(/step:400 loss:0\.5/)).toBeInTheDocument();
    expect(screen.queryByText("No log lines yet.")).toBeNull();
  });

  it("charts: distinct tick labels for lr ~1e-5 and point markers for a single logged step", async () => {
    server.use(
      http.get("/runs/{run_id}/metrics", () =>
        HttpResponse.json({
          run_id: f.IDS.run2,
          series: [
            { key: "loss", steps: [200], values: [0.9], has_nonfinite: false, downsampled: false },
            { key: "lr", steps: [200], values: [1e-5], has_nonfinite: false, downsampled: false },
          ],
        }),
      ),
    );
    renderApp(`/w/robot-lab/runs/${f.IDS.run2}`);
    await screen.findByRole("img", { name: /Learning rate chart/ });
    const lr = plots().find((p) => p.el.getAttribute("data-uplot-series") === "Step|lr");
    expect(lr).toBeDefined();
    const yTicks = lr?.opts.axes[1]?.values?.(null, [1e-5, 2e-5, 3e-5]);
    expect(yTicks).toEqual(["1e-5", "2e-5", "3e-5"]);
    expect(lr?.opts.series[1]?.points?.show).toBe(showPoints);
    expect(showPoints({ data: [[200], [1e-5]] }, 1)).toBe(true);
    expect(showPoints({ data: [Array.from({ length: 500 }, (_, i) => i), Array(500).fill(1)] }, 1)).toBe(
      false,
    );
    expect(axisValues("vi")(null, [2500, 10000])).toEqual(["2.500", "10.000"]);
  });
});

describe("recovery helpers", () => {
  it("maps error codes to actions allowed for the run", () => {
    const gpus = [
      { id: "cuda0", name: "NVIDIA GeForce RTX 3060", status: "online" as const },
      { id: "cuda1", name: "Tesla P40", status: "online" as const },
    ];
    expect(recoveryActions({ error_code: "oom", allowed_actions: ["clone"], gpu_id: "cuda0" }, gpus)).toEqual(
      [
        { kind: "clone", adjust: "half_batch" },
        { kind: "clone_gpu", gpu: "cuda1" },
      ],
    );
    expect(recoveryActions({ error_code: "oom", allowed_actions: ["clone"], gpu_id: "cuda1" }, gpus)).toEqual(
      [{ kind: "clone", adjust: "half_batch" }],
    );
    expect(recoveryActions({ error_code: "nan_loss", allowed_actions: ["clone"], gpu_id: null })).toEqual([
      { kind: "clone", adjust: "lower_lr" },
    ]);
    expect(
      recoveryActions({ error_code: "config_invalid", allowed_actions: ["clone"], gpu_id: null }),
    ).toEqual([{ kind: "clone_edit" }]);
    expect(recoveryActions({ error_code: "stalled", allowed_actions: ["resume"], gpu_id: null })).toEqual([
      { kind: "resume" },
    ]);
    expect(recoveryActions({ error_code: "stalled", allowed_actions: [], gpu_id: null })).toEqual([]);
    expect(recoveryActions({ error_code: null, allowed_actions: ["clone"], gpu_id: null })).toEqual([]);
    expect(cloneHref("r1", { kind: "clone_gpu", gpu: "cuda1" })).toBe("runs/new?clone=r1&gpu=cuda1");
  });

  it("applies clone adjustments", () => {
    expect(applyCloneAdjust({ policy: {}, train: { batch_size: 1 } }, "half_batch").train.batch_size).toBe(1);
    const lr = applyCloneAdjust({ policy: { optimizer_lr: 1e-5 }, train: {} }, "lower_lr");
    expect(lr.policy.optimizer_lr).toBe(1e-6);
    expect(lr.changed).toEqual({ field: "optimizer_lr", from: 1e-5, to: 1e-6 });
    expect(applyCloneAdjust({ policy: {}, train: {} }, null).changed).toBeNull();
  });
});
