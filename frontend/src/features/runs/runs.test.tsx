import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import * as f from "@/test/fixtures";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderApp } from "@/test/render";
import { http, server } from "@/test/server";

describe("runs list and compare", () => {
  it("lists runs with status and progress; compare needs 2..8 selected", async () => {
    const { router } = renderApp("/w/robot-lab/runs");
    expect(await screen.findByRole("link", { name: "#7 act-picknplace" })).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Running")).toBeInTheDocument();
    expect(within(table).getByText("Succeeded")).toBeInTheDocument();
    const compare = screen.getByRole("button", { name: /Compare/ });
    expect(compare).toBeDisabled();
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox", { name: "Select act-picknplace for comparison" }));
    await user.click(screen.getByRole("checkbox", { name: "Select act-baseline for comparison" }));
    expect(compare).toBeEnabled();
    await user.click(compare);
    expect(router.state.location.pathname).toBe("/w/robot-lab/runs/compare");
  });

  it("passes status filters and 'mine' to listRuns", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/runs", ({ request }) => {
        seen.push(new URL(request.url).search);
        return HttpResponse.json({ items: [f.run], next_cursor: null });
      }),
    );
    renderApp("/w/robot-lab/runs");
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Status"), "failed");
    await user.click(screen.getByRole("checkbox", { name: "Only my runs" }));
    await waitFor(() => {
      expect(seen.some((s) => s.includes("status=failed") && s.includes("created_by=me"))).toBe(true);
    });
  });

  it("compare overlays one series per run and shows the config diff", async () => {
    server.use(
      http.get("/runs/compare", () =>
        HttpResponse.json({
          runs: [f.run, f.run2],
          series: [
            { run_id: f.IDS.run, series: [{ key: "loss", steps: [1, 2], values: [2, 1] }] },
            { run_id: f.IDS.run2, series: [{ key: "loss", steps: [1, 2], values: [3, 1.5] }] },
          ],
          config_diff: [{ path: "policy.chunk_size", values: [100, 50] }],
        }),
      ),
    );
    renderApp(`/w/robot-lab/runs/compare?ids=${f.IDS.run},${f.IDS.run2}`);
    expect(await screen.findByText("policy.chunk_size")).toBeInTheDocument();
    const chart = await screen.findByRole("img", { name: /loss chart/ });
    expect(chart).toHaveAttribute("data-uplot-series", "Step|#7 act-picknplace|#6 act-baseline");
  });
});

describe("run detail (live via SSE)", () => {
  const original = globalThis.EventSource;
  beforeEach(() => {
    FakeEventSource.reset();
    globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
  });
  afterEach(() => {
    globalThis.EventSource = original;
  });

  it("bootstraps metrics, goes live after the last persisted seq and applies events", async () => {
    server.use(
      http.get("/runs/{run_id}/events/history", () => HttpResponse.json({ items: [], last_seq: 17 })),
    );
    renderApp(`/w/robot-lab/runs/${f.IDS.run}`);
    expect(await screen.findByText("Step 2,500 of 10,000 (25%)")).toBeInTheDocument();
    await waitFor(() => {
      expect(FakeEventSource.instances.length).toBeGreaterThan(0);
    });
    await waitFor(() => {
      expect(FakeEventSource.instances.some((e) => e.url.includes("/runs/"))).toBe(true);
    });
    const es = FakeEventSource.instances.find((e) => e.url.includes("/runs/"))!;
    expect(es.url).toContain(`/api/v1/runs/${f.IDS.run}/events?after_seq=17`);
    const lossChart = await screen.findByRole("img", { name: /Loss chart/ });
    expect(lossChart).toHaveAttribute("data-uplot-series", "Step|loss");

    act(() => {
      es.open();
      es.emit("progress", {
        kind: "progress",
        step: 2600,
        total_steps: 10000,
        steps_per_s: 9,
        eta_s: 822,
        ts: f.T0,
      });
      es.emit("metrics", { kind: "metrics", step: 800, values: { loss: 0.7 }, ts: f.T0 }, 18);
      es.emit("log", { kind: "log", byte_offset: 4096, lines: ["step:2600 smpl:21K loss:0.700"] });
      es.emit("warning", { kind: "warning", code: "vram_near_limit", message: "VRAM", ts: f.T0 }, 19);
    });
    expect(await screen.findByText("Step 2,600 of 10,000 (26%)")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText("GPU memory is close to the limit.")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Logs" }));
    expect(await screen.findByText(/step:2600 smpl:21K/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download .log/ })).toHaveAttribute(
      "href",
      `${window.location.origin}/api/v1/runs/${f.IDS.run}/logs?download=true`,
    );

    await user.click(screen.getByRole("tab", { name: "GPU" }));
    expect(await screen.findByText("87 %")).toBeInTheDocument();
  });

  it("pause offers next-checkpoint vs now and posts the mode", async () => {
    let mode = "";
    server.use(
      http.post("/runs/{run_id}/pause", async ({ request }) => {
        mode = (await request.json())?.mode ?? "";
        return HttpResponse.json({ ...f.run, status: "pausing" }, { status: 202 });
      }),
    );
    renderApp(`/w/robot-lab/runs/${f.IDS.run}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Pause" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("Training continues until step 5,000, saves, then stops."),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole("radio", { name: /Now/ }));
    await user.click(within(dialog).getByRole("button", { name: "Pause" }));
    await waitFor(() => {
      expect(mode).toBe("now");
    });
  });

  it("cancel asks for confirmation", async () => {
    let cancelled = false;
    server.use(
      http.post("/runs/{run_id}/cancel", () => {
        cancelled = true;
        return HttpResponse.json({ ...f.run, status: "cancelling" }, { status: 202 });
      }),
    );
    renderApp(`/w/robot-lab/runs/${f.IDS.run}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Cancel run" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel run" }));
    await waitFor(() => {
      expect(cancelled).toBe(true);
    });
  });

  it("finished run: no SSE, checkpoints with model link, eval result with disclaimer", async () => {
    server.use(
      http.get("/runs/{run_id}/checkpoints", () =>
        HttpResponse.json({ items: [{ ...f.checkpoint, eval_summary: { action_mae: 0.03 } }] }),
      ),
      http.get("/runs/{run_id}/checkpoints/{step}/eval-result", () =>
        HttpResponse.json({
          schema_version: "1",
          run_id: f.IDS.run2,
          step: 10000,
          heldout_episodes: [3, 11],
          n_frames: 1100,
          action_names: f.JOINTS,
          overall: { mae: 0.031, mse: 0.002 },
          per_joint: f.JOINTS.map((name) => ({ name, mae: 0.03, mse: 0.002 })),
          disclaimer_key: "eval.offline_not_success_rate",
        }),
      ),
    );
    renderApp(`/w/robot-lab/runs/${f.IDS.run2}?tab=checkpoints`);
    expect((await screen.findAllByText("10,000")).length).toBeGreaterThan(0);
    // only the workspace stream (AppShell) is open; a finished run opens no run stream
    expect(FakeEventSource.instances.filter((e) => e.url.includes("/runs/"))).toHaveLength(0);
    expect(FakeEventSource.instances.some((e) => e.url.includes(`/workspaces/${f.IDS.ws}/events`))).toBe(
      true,
    );
    const user = userEvent.setup();
    expect(screen.getAllByRole("link", { name: "Open model" })[0]).toHaveAttribute(
      "href",
      `/w/robot-lab/models/${f.IDS.model}`,
    );
    await user.click(screen.getByRole("button", { name: "View" }));
    expect((await screen.findAllByText(/not a success rate on the real robot/)).length).toBe(2);
    expect(screen.getAllByText("gripper.pos").length).toBeGreaterThan(0);
  });

  it("shows the localised run error for failed runs", async () => {
    server.use(
      http.get("/runs/{run_id}", () =>
        HttpResponse.json({
          ...f.run2,
          status: "failed",
          error_code: "oom",
          error_message: "CUDA out of memory",
        }),
      ),
    );
    renderApp(`/w/robot-lab/runs/${f.IDS.run2}`);
    expect(
      await screen.findByText("Out of GPU memory. Reduce batch size or use the P40."),
    ).toBeInTheDocument();
    expect(screen.getByText("CUDA out of memory")).toBeInTheDocument();
  });
});
