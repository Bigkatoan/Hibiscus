import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, problemResponse, server } from "@/test/server";
import { SLUG_RE, slugify } from "./admin/CreateWorkspaceDialog";

describe("workspace / dataset management", () => {
  it("slugify produces contract-valid slugs (Vietnamese diacritics stripped)", () => {
    expect(slugify("Phòng Lab Đà Nẵng")).toBe("phong-lab-da-nang");
    expect(SLUG_RE.test(slugify("Phòng Lab Đà Nẵng"))).toBe(true);
    expect(slugify("  --Robot__Lab!! ")).toBe("robot-lab");
    expect(slugify("x".repeat(60))).toHaveLength(40);
  });

  it("platform admin creates a workspace and lands on its settings", async () => {
    let body: unknown = null;
    server.use(
      http.post("/workspaces", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { ...f.workspace, id: f.IDS.ws2, slug: "phong-lab", name: "Phòng Lab" },
          { status: 201 },
        );
      }),
    );
    const { router } = renderApp("/admin/users");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /New workspace/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Workspace name/), "Phòng Lab");
    expect(within(dialog).getByLabelText(/URL name/)).toHaveValue("phong-lab");
    await user.click(within(dialog).getByRole("button", { name: /New workspace/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/w/phong-lab/settings");
    });
    expect(body).toEqual({ name: "Phòng Lab", slug: "phong-lab" });
  });

  it("shows workspace_slug_taken on the slug field", async () => {
    server.use(http.post("/workspaces", () => problemResponse(409, "workspace_slug_taken")));
    renderApp("/admin/users");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /New workspace/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Workspace name/), "Robot Lab");
    await user.click(within(dialog).getByRole("button", { name: /New workspace/ }));
    expect(await within(dialog).findByText("This workspace URL is taken.")).toBeInTheDocument();
  });

  it("owner deletes the workspace; workspace_not_empty is explained", async () => {
    let calls = 0;
    server.use(
      http.delete("/workspaces/{workspace_id}", ({ response }) => {
        calls += 1;
        return calls === 1 ? problemResponse(409, "workspace_not_empty") : response(204).empty();
      }),
    );
    const { router } = renderApp("/w/robot-lab/settings");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Delete workspace/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete workspace" }));
    expect(
      await within(dialog).findByText("Stop active runs before deleting the workspace."),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete workspace" }));
    await waitFor(() => {
      expect(router.state.location.pathname).not.toBe("/w/robot-lab/settings");
    });
  });

  it("non-owners have no danger zone", async () => {
    renderApp("/w/side-project/settings");
    await screen.findByRole("tab", { name: "Members" });
    expect(screen.queryByRole("button", { name: /Delete workspace/ })).not.toBeInTheDocument();
  });

  it("edits a dataset and maps dataset_name_taken to the name field", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch("/datasets/{dataset_id}", async ({ request }) => {
        bodies.push(await request.json());
        if (bodies.length === 1) return problemResponse(409, "dataset_name_taken");
        return HttpResponse.json({ ...f.dataset, name: "so101 v2" });
      }),
    );
    renderApp(`/w/robot-lab/datasets/${f.IDS.dataset}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Edit dataset/ }));
    const dialog = await screen.findByRole("dialog");
    const name = within(dialog).getByLabelText(/^Name/);
    await user.clear(name);
    await user.type(name, "taken");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText("A dataset with this name already exists.")).toBeInTheDocument();
    await user.clear(name);
    await user.type(name, "so101 v2");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(bodies[1]).toEqual({ name: "so101 v2", description: f.dataset.description });
  });

  it("cancels a running validation job", async () => {
    let cancelled = false;
    server.use(
      http.post("/dataset-versions/{version_id}/validation", () =>
        HttpResponse.json({ ...f.job, status: "running", progress: 0.3 }, { status: 202 }),
      ),
      http.get("/jobs/{job_id}", () =>
        HttpResponse.json({ ...f.job, status: cancelled ? "cancelled" : "running", progress: 0.3 }),
      ),
      http.post("/jobs/{job_id}/cancel", () => {
        cancelled = true;
        return HttpResponse.json({ ...f.job, status: "cancelled" }, { status: 202 });
      }),
    );
    renderApp(`/w/robot-lab/datasets/${f.IDS.dataset}?tab=validation`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Run validation again/ }));
    await user.click(await screen.findByRole("button", { name: "Cancel validation" }));
    expect(await screen.findByText("Cancelled")).toBeInTheDocument();
    expect(cancelled).toBe(true);
  });
});
