import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, problemResponse, server } from "@/test/server";

function fieldBox(name: string): HTMLElement {
  const el = document.querySelector<HTMLElement>(`[data-field="${name}"]`);
  if (!el) throw new Error(`field ${name} not rendered`);
  return el;
}

describe("training wizard", () => {
  it("dataset -> policy -> schema form -> preflight -> createRun", async () => {
    const created: Schemas["RunCreate"][] = [];
    const preflights: Schemas["RunCreate"][] = [];
    server.use(
      http.post("/runs/preflight", async ({ request }) => {
        preflights.push(await request.json());
        return HttpResponse.json(f.preflightOk);
      }),
      http.post("/runs", async ({ request }) => {
        expect(request.headers.get("Idempotency-Key")).toMatch(/^fe-/);
        created.push(await request.json());
        return HttpResponse.json(f.run, { status: 201 });
      }),
    );
    const { router } = renderApp("/w/robot-lab/runs/new");
    const user = userEvent.setup();

    // 1. dataset
    await user.selectOptions(await screen.findByLabelText(/^Dataset/), f.IDS.dataset);
    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /v1/ })).toBeChecked();
    });
    await user.click(screen.getByRole("button", { name: /Next/ }));

    // 2. policy (TD-MPC is blocked: no next.reward in the dataset)
    expect(await screen.findByText("This dataset has no next.reward feature.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /TD-MPC/ })).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: /ACT/ }));
    await user.click(screen.getByRole("button", { name: /Next/ }));

    // 3. form rendered from the real act.json/train.json
    await screen.findByText("Chunk size");
    const steps = within(fieldBox("steps")).getByRole("spinbutton");
    expect(steps).toHaveValue(10000); // quick preset
    const chunk = within(fieldBox("chunk_size")).getByRole("spinbutton");
    await user.clear(chunk);
    await user.type(chunk, "50");
    // n_action_steps (100) > chunk_size (50) violates the cross-field rule
    expect(
      await within(fieldBox("n_action_steps")).findByText("Violates rule: n_action_steps <= chunk_size."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review/ })).toBeDisabled();
    const nAct = within(fieldBox("n_action_steps")).getByRole("spinbutton");
    await user.clear(nAct);
    await user.type(nAct, "50");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Review/ })).toBeEnabled();
    });
    expect(within(fieldBox("chunk_size")).getByText("changed")).toBeInTheDocument();

    // switching preset re-bases the form
    await user.click(screen.getByRole("radio", { name: "Standard (100k steps)" }));
    await waitFor(() => {
      expect(within(fieldBox("steps")).getByRole("spinbutton")).toHaveValue(100000);
    });
    await user.click(screen.getByRole("radio", { name: "Quick (10k steps)" }));
    await user.clear(within(fieldBox("chunk_size")).getByRole("spinbutton"));
    await user.type(within(fieldBox("chunk_size")).getByRole("spinbutton"), "50");
    await user.clear(within(fieldBox("n_action_steps")).getByRole("spinbutton"));
    await user.type(within(fieldBox("n_action_steps")).getByRole("spinbutton"), "50");

    // advanced tab
    await user.click(screen.getByRole("tab", { name: "Advanced" }));
    const dropout = within(await waitFor(() => fieldBox("dropout"))).getByRole("spinbutton");
    await user.clear(dropout);
    await user.type(dropout, "0.2");
    await user.type(screen.getByLabelText(/Run name/), "act-test");

    // 4. review
    await user.click(screen.getByRole("button", { name: /Review/ }));
    expect(await screen.findByText("Measured with a 20-step dry run.")).toBeInTheDocument();
    expect(screen.getAllByText("Mixed precision").length).toBeGreaterThan(0);
    expect(screen.getByText(/--policy.type=act/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Start training/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/robot-lab/runs/${f.IDS.run}`);
    });

    expect(preflights).toHaveLength(1);
    const req = created[0];
    expect(req).toMatchObject({
      workspace_id: f.IDS.ws,
      dataset_version_id: f.IDS.version,
      policy_type: "act",
      preset: "quick",
      name: "act-test",
      gpu: "auto",
      heldout_fraction: 0.1,
      export: { onnx: true, onnx_fp16: false, eval: true },
      seed: null,
    });
    expect(req?.config.policy).toMatchObject({
      chunk_size: 50,
      n_action_steps: 50,
      dropout: 0.2,
      use_vae: true,
    });
    expect(req?.config.policy).not.toHaveProperty("n_heads");
    expect(req?.config.train).toMatchObject({
      steps: 10000,
      batch_size: 8,
      save_freq: 5000,
      mixed_precision: "no",
    });
  });

  it("blocks start when preflight fails and shows the localised checks", async () => {
    server.use(
      http.post("/runs/preflight", () =>
        HttpResponse.json({
          ...f.preflightOk,
          ok: false,
          checks: [
            {
              id: "vram",
              severity: "error",
              code: "gpu_insufficient_vram",
              message: "needs 30 GB",
              params: {},
            },
          ],
        }),
      ),
    );
    renderApp(`/w/robot-lab/runs/new?version=${f.IDS.version}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: /ACT/ }));
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await screen.findByText("Chunk size");
    await user.click(screen.getByRole("button", { name: /Review/ }));
    expect(await screen.findByText("GPU memory")).toBeInTheDocument();
    // check `code` is an ErrorCode -> localised via errors.*, never the English `message`
    expect(screen.getByText("Not enough GPU memory for this configuration.")).toBeInTheDocument();
    expect(screen.queryByText("needs 30 GB")).not.toBeInTheDocument();
    expect(screen.getByText("Fix the errors above before starting.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start training/ })).toBeDisabled();
  });

  it("upload -> train golden path: ACT preselected, Next, Review, Start (3 clicks in the wizard)", async () => {
    let created = false;
    server.use(
      http.post("/runs", () => {
        created = true;
        return HttpResponse.json(f.run, { status: 201 });
      }),
    );
    const { router } = renderApp(`/w/robot-lab/runs/new?version=${f.IDS.version}`);
    const user = userEvent.setup();
    expect(await screen.findByRole("radio", { name: /ACT/ })).toBeChecked();
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await screen.findByText("Chunk size");
    await user.click(screen.getByRole("button", { name: /Review/ }));
    await user.click(await screen.findByRole("button", { name: /Start training/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/robot-lab/runs/${f.IDS.run}`);
    });
    expect(created).toBe(true);
  });

  it("shows createRun errors (quota) without leaving the review step", async () => {
    server.use(http.post("/runs", () => problemResponse(403, "quota_exceeded")));
    renderApp(`/w/robot-lab/runs/new?version=${f.IDS.version}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: /ACT/ }));
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await screen.findByText("Chunk size");
    await user.click(screen.getByRole("button", { name: /Review/ }));
    await user.click(await screen.findByRole("button", { name: /Start training/ }));
    expect(
      await screen.findByText("Quota exceeded. Free space or ask an admin to raise the limit."),
    ).toBeInTheDocument();
  });

  it("clone prefills from the source run and calls cloneRun", async () => {
    let cloneBody: unknown = null;
    server.use(
      http.post("/runs/{run_id}/clone", async ({ request }) => {
        cloneBody = await request.json();
        return HttpResponse.json({ ...f.run, id: f.IDS.run2 }, { status: 201 });
      }),
    );
    const { router } = renderApp(`/w/robot-lab/runs/new?clone=${f.IDS.run}`);
    expect(await screen.findByRole("heading", { name: "Clone act-picknplace" })).toBeInTheDocument();
    await screen.findByText("Chunk size");
    expect(screen.getByLabelText(/Run name/)).toHaveValue("act-picknplace-clone");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Review/ }));
    await user.click(await screen.findByRole("button", { name: /Start training/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/robot-lab/runs/${f.IDS.run2}`);
    });
    expect(cloneBody).toMatchObject({ dataset_version_id: f.IDS.version, name: "act-picknplace-clone" });
  });
});
