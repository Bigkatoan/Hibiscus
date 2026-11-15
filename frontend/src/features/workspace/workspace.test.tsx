import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { qk } from "@/api/hooks/keys";
import { testQueryClient } from "@/test/render";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, problemResponse, server } from "@/test/server";
import { roleAtLeast } from "./context";
import { applyWorkspaceEvent } from "./useWorkspaceEvents";

describe("workspace settings", () => {
  it("lists members and changes a role", async () => {
    let patched: unknown = null;
    server.use(
      http.patch("/workspaces/{workspace_id}/members/{user_id}", async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json({ ...f.members[1]!, role: "admin" });
      }),
    );
    renderApp("/w/robot-lab/settings/members");
    const select = await screen.findByRole("combobox", { name: "Role for Binh Tran" });
    // the owner cannot edit their own role
    expect(screen.queryByRole("combobox", { name: "Role for An Nguyen" })).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.selectOptions(select, "admin");
    await waitFor(() => {
      expect(patched).toEqual({ role: "admin" });
    });
  });

  it("shows the last_owner conflict localised", async () => {
    server.use(
      http.patch("/workspaces/{workspace_id}/members/{user_id}", () => problemResponse(409, "last_owner")),
    );
    renderApp("/w/robot-lab/settings/members");
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByRole("combobox", { name: "Role for Binh Tran" }), "viewer");
    expect(await screen.findByText("A workspace needs at least one owner.")).toBeInTheDocument();
  });

  it("creates an invite and shows the manual link when email is disabled", async () => {
    server.use(
      http.post("/workspaces/{workspace_id}/invites", () =>
        HttpResponse.json(
          { ...f.invite, accept_url: "https://robot.example.com/invite?token=abc" },
          { status: 201 },
        ),
      ),
    );
    renderApp("/w/robot-lab/settings/invites");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/Email/), "chi@example.com");
    await user.click(screen.getByRole("button", { name: /Send invite/ }));
    expect(await screen.findByText("https://robot.example.com/invite?token=abc")).toBeInTheDocument();
    expect(screen.getByText("chi@example.com")).toBeInTheDocument();
  });

  it("shows usage against quotas", async () => {
    renderApp("/w/robot-lab/settings");
    expect(await screen.findByText("3 GiB / 200 GiB")).toBeInTheDocument();
    expect(screen.getByText("12.5 / 200")).toBeInTheDocument();
  });

  it("viewers do not get the invites tab", async () => {
    renderApp("/w/side-project/settings");
    await screen.findByRole("tab", { name: "Members" });
    expect(screen.queryByRole("tab", { name: "Invites" })).not.toBeInTheDocument();
  });

  it("creates a PAT and shows it exactly once", async () => {
    let body: unknown = null;
    server.use(
      http.post("/auth/tokens", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { ...f.apiToken, token: "hbp_ab12cd34_secretsecretsecretsecretsecretsecret1234567" },
          { status: 201 },
        );
      }),
    );
    renderApp("/w/robot-lab/settings/tokens");
    const user = userEvent.setup();
    expect(await screen.findByText("collect-pc")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Create token/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Name/), "lab-pc");
    // Default preset "Collection machine" covers push / train / logs / pull (CX-03).
    expect(within(dialog).getByRole("radio", { name: "Collection machine" })).toBeChecked();
    for (const s of ["datasets:write", "runs:write", "runs:read", "models:read"])
      expect(within(dialog).getByRole("checkbox", { name: new RegExp(s) })).toBeChecked();
    await user.selectOptions(within(dialog).getByLabelText(/Expires/), "never");
    await user.click(within(dialog).getByRole("button", { name: /Create token/ }));
    expect(await within(dialog).findByTestId("new-token")).toHaveTextContent("hbp_ab12cd34_secret");
    expect(within(dialog).getByText("Copy this token now. It is shown only once.")).toBeInTheDocument();
    expect(body).toEqual({
      name: "lab-pc",
      workspace_id: f.IDS.ws,
      scopes: ["datasets:read", "datasets:write", "runs:read", "runs:write", "models:read"],
      expires_in_days: null,
    });
    // The hint never puts the token on the command line (shell history).
    expect(within(dialog).getByTestId("login-cmd")).toHaveTextContent(
      `hibiscus login --server ${window.location.origin}`,
    );
    expect(dialog.textContent).not.toMatch(/--token/);
    // Cannot lose the one-time token: Esc and the X are ignored until "I have copied" is ticked.
    expect(within(dialog).queryByRole("button", { name: "Close" })).toBeNull();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const done = within(dialog).getByRole("button", { name: "Done" });
    expect(done).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox", { name: "I have copied the token" }));
    await user.click(done);
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("token presets: read only, custom when scopes are edited", async () => {
    let body: unknown = null;
    server.use(
      http.post("/auth/tokens", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...f.apiToken, token: "hbp_ab12cd34_x" }, { status: 201 });
      }),
    );
    renderApp("/w/robot-lab/settings/tokens");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Create token/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Name/), "viewer-pc");
    await user.click(within(dialog).getByRole("radio", { name: "Read only" }));
    expect(within(dialog).getByRole("checkbox", { name: /runs:write/ })).not.toBeChecked();
    await user.click(within(dialog).getByRole("checkbox", { name: /datasets:write/ }));
    expect(within(dialog).getByRole("radio", { name: "Custom" })).toBeChecked();
    await user.click(within(dialog).getByRole("checkbox", { name: /datasets:write/ }));
    expect(within(dialog).getByRole("radio", { name: "Read only" })).toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: /Create token/ }));
    await within(dialog).findByTestId("new-token");
    expect(body).toMatchObject({ scopes: ["datasets:read", "runs:read", "models:read"] });
  });

  it("token list shows where a token was last used", async () => {
    server.use(
      http.get("/auth/tokens", () =>
        HttpResponse.json({ items: [{ ...f.apiToken, last_used_at: f.T0, last_used_ip: "192.0.2.7" }] }),
      ),
    );
    renderApp("/w/robot-lab/settings/tokens");
    expect(await screen.findByText("from 192.0.2.7")).toBeInTheDocument();
  });
});

describe("workspace helpers", () => {
  it("ranks roles", () => {
    expect(roleAtLeast("owner", "admin")).toBe(true);
    expect(roleAtLeast("viewer", "member")).toBe(false);
  });

  it("invalidates caches from workspace stream events", () => {
    const qc = testQueryClient();
    qc.setQueryData(qk.run(f.IDS.run), f.run);
    qc.setQueryData(qk.model(f.IDS.model), f.model);
    applyWorkspaceEvent(qc, f.IDS.ws, { event: "run.status", id: 1, data: { run_id: f.IDS.run } });
    applyWorkspaceEvent(qc, f.IDS.ws, { event: "model.status", id: null, data: { id: f.IDS.model } });
    applyWorkspaceEvent(qc, f.IDS.ws, { event: "heartbeat", id: null, data: {} });
    expect(qc.getQueryState(qk.run(f.IDS.run))?.isInvalidated).toBe(true);
    expect(qc.getQueryState(qk.model(f.IDS.model))?.isInvalidated).toBe(true);
  });
});
