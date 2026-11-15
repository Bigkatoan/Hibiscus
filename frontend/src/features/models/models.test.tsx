import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, server } from "@/test/server";

describe("models", () => {
  it("lists models with verified + ONNX badges and a download link", async () => {
    renderApp("/w/robot-lab/models");
    expect(await screen.findByRole("link", { name: "act-picknplace" })).toHaveAttribute(
      "href",
      `/w/robot-lab/models/${f.IDS.model}`,
    );
    const row = screen.getByRole("link", { name: "act-picknplace" }).closest("tr")!;
    expect(within(row).getByText("Verified")).toBeInTheDocument();
    expect(within(row).getByText("ONNX: passed")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Download act-picknplace" })).toHaveAttribute(
      "href",
      `${window.location.origin}/api/v1/models/${f.IDS.model}/download`,
    );
  });

  it("filters verified only", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("/models", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("verified"));
        return HttpResponse.json({ items: [f.model], next_cursor: null });
      }),
    );
    renderApp("/w/robot-lab/models");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Verified only" }));
    await waitFor(() => {
      expect(seen).toContain("true");
    });
  });

  it("detail shows the three verification checks, files and CLI pull command", async () => {
    renderApp(`/w/robot-lab/models/${f.IDS.model}`);
    expect(await screen.findByText("Loads with PreTrainedPolicy.from_pretrained")).toBeInTheDocument();
    expect(screen.getByText("ONNX parity within tolerance")).toBeInTheDocument();
    expect(screen.getByText("MANIFEST hashes match")).toBeInTheDocument();
    expect(screen.getAllByText("passed").length).toBeGreaterThanOrEqual(3);
    expect(await screen.findByText("Files in act-picknplace-r6-step10000")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "onnx/model.onnx" })).toHaveAttribute(
      "href",
      `${window.location.origin}/api/v1/models/${f.IDS.model}/files/onnx/model.onnx`,
    );
    // --to is the parent folder: pull itself creates <to>/<bundle_name> (CX-09).
    expect(screen.getAllByText(`hibiscus pull ${f.IDS.model} --to ~/lelab/models`).length).toBeGreaterThan(0);
    expect(screen.getByText("cd ~/lelab/models/act-picknplace-r6-step10000")).toBeInTheDocument();
  });

  it("not verified models show why", async () => {
    server.use(
      http.get("/models/{model_id}", () =>
        HttpResponse.json({
          ...f.model,
          verified: false,
          onnx_status: "not_supported",
          verification: { load_ok: true, parity_ok: null, manifest_ok: true, checked_at: f.T0 },
        }),
      ),
    );
    renderApp(`/w/robot-lab/models/${f.IDS.model}`);
    expect(await screen.findByText("Not verified")).toBeInTheDocument();
    expect(screen.getByText("ONNX: not supported")).toBeInTheDocument();
    expect(screen.getByText("not applicable")).toBeInTheDocument();
  });

  it("pushes to the Hub when an HF token is stored", async () => {
    let body: unknown = null;
    server.use(
      http.get("/users/me/secrets/hf-token", () =>
        HttpResponse.json({ present: true, hint: "hf_…abcd", updated_at: f.T0 }),
      ),
      http.post("/models/{model_id}/push-hub", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...f.job, kind: "push_model_hub" }, { status: 202 });
      }),
    );
    renderApp(`/w/robot-lab/models/${f.IDS.model}`);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/Repository/), "your-hf-user/act-picknplace");
    await user.click(screen.getByRole("button", { name: "Push" }));
    expect(await screen.findByText("Push queued.")).toBeInTheDocument();
    expect(body).toEqual({ repo_id: "your-hf-user/act-picknplace", private: true, include_onnx: true });
  });

  it("asks for an HF token before pushing", async () => {
    renderApp(`/w/robot-lab/models/${f.IDS.model}`);
    expect(await screen.findByText("Add a Hugging Face token in your account first.")).toBeInTheDocument();
  });
});
