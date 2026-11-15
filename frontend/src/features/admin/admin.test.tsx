import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, server } from "@/test/server";

describe("admin", () => {
  it("is hidden from non platform admins", async () => {
    server.use(
      http.get("/auth/me", () =>
        HttpResponse.json({ ...f.me, user: { ...f.user, is_platform_admin: false } }),
      ),
    );
    renderApp("/admin/users");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });

  it("users: disable, reset link, revoke sessions", async () => {
    const calls: string[] = [];
    server.use(
      http.patch("/admin/users/{user_id}", async ({ request }) => {
        calls.push(`patch:${JSON.stringify(await request.json())}`);
        return HttpResponse.json({ ...f.adminUser, is_active: false });
      }),
      http.post("/admin/users/{user_id}/password-reset-link", () =>
        HttpResponse.json(
          { url: "https://robot.example.com/reset-password#token=xyz", expires_at: f.T0 },
          { status: 201 },
        ),
      ),
      http.post("/admin/users/{user_id}/revoke-sessions", ({ response }) => {
        calls.push("revoke");
        return response(204).empty();
      }),
    );
    renderApp("/admin/users");
    const user = userEvent.setup();
    const row = (await screen.findByText("an@example.com")).closest("tr")!;
    await user.click(within(row).getByRole("switch", { name: "Account active for An Nguyen" }));
    await user.click(within(row).getByRole("button", { name: "Create password reset link" }));
    expect(
      await within(row).findByText("https://robot.example.com/reset-password#token=xyz"),
    ).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Sign out all sessions" }));
    await waitFor(() => {
      expect(calls).toEqual(['patch:{"is_active":false}', "revoke"]);
    });
  });

  it("audit log lists events and filters by action", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("/admin/audit-events", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("action"));
        return HttpResponse.json({ items: [f.auditEvent], next_cursor: null });
      }),
    );
    renderApp("/admin/audit");
    expect(await screen.findByText("auth.login")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Action"), "run.created");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => {
      expect(seen).toContain("run.created");
    });
  });

  it("quotas: upsert the workspace default", async () => {
    let body: unknown = null;
    server.use(
      http.put("/admin/workspaces/{workspace_id}/quotas", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(f.quota);
      }),
    );
    renderApp("/admin/quotas");
    const user = userEvent.setup();
    const field = await screen.findByLabelText("Max concurrent runs");
    await waitFor(() => {
      expect(field).toHaveValue(1);
    });
    await user.clear(field);
    await user.type(field, "2");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(body).toEqual({
        user_id: null,
        max_concurrent_runs: 2,
        max_queued_runs: 10,
        gpu_hours_per_month: 200,
        storage_bytes: 200 * 1024 ** 3,
        max_upload_bytes: 50 * 1024 ** 3,
      });
    });
  });

  it("gpus: drain a GPU", async () => {
    let status = "";
    server.use(
      http.patch("/admin/gpus/{gpu_id}", async ({ request }) => {
        status = (await request.json()).status;
        return HttpResponse.json({ ...f.gpus[1]!, status: "draining" });
      }),
    );
    renderApp("/admin/gpus");
    const user = userEvent.setup();
    expect(await screen.findByText("cuda1 · Tesla P40")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Drain" })[1]!);
    await waitFor(() => {
      expect(status).toBe("draining");
    });
  });

  it("system page shows versions and email provider", async () => {
    renderApp("/admin/system");
    expect(await screen.findByText("Cloudflare Email Service · Enabled")).toBeInTheDocument();
    expect(screen.getByText("hibiscus-datasets")).toBeInTheDocument();
  });
});
