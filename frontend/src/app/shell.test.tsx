import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { i18n } from "@/lib/i18n";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, problemResponse, server } from "@/test/server";
import { safeNext } from "./guards";

async function axeViolations(): Promise<string[]> {
  // color-contrast needs layout/canvas (not available in jsdom); verified manually via tokens.
  const res = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  return res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

describe("app shell", () => {
  it("redirects / to the first workspace and renders navigation", async () => {
    const { router } = renderApp("/");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/w/robot-lab/datasets");
    });
    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getByRole("link", { name: "Training runs" })).toHaveAttribute(
      "href",
      "/w/robot-lab/runs",
    );
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
  });

  it("switches workspace from the switcher", async () => {
    const { router } = renderApp("/w/robot-lab/datasets");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Switch workspace" }));
    await user.click(await screen.findByRole("menuitemradio", { name: /Side Project/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/w/side-project/datasets");
    });
  });

  it("switches language and stores it on the profile", async () => {
    let patched: unknown = null;
    server.use(
      http.patch("/users/me", async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json({ ...f.user, locale: "vi" });
      }),
    );
    renderApp("/w/robot-lab/datasets");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Language" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Tiếng Việt" }));
    await waitFor(() => {
      expect(patched).toEqual({ locale: "vi" });
    });
    expect(document.documentElement.lang).toBe("vi");
    await i18n.changeLanguage("en");
  });

  it("toggles dark mode", async () => {
    renderApp("/w/robot-lab/datasets");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Theme" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Dark" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    await user.click(screen.getByRole("button", { name: "Theme" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Light" }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("shows notifications with unread count and marks one read", async () => {
    let read = "";
    server.use(
      http.post("/notifications/{notification_id}/read", ({ params, response }) => {
        read = params.notification_id;
        return response(204).empty();
      }),
    );
    const { router } = renderApp("/w/robot-lab/datasets");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Notifications (1 unread)" }));
    await user.click(await screen.findByRole("menuitem", { name: /Run act-baseline finished/ }));
    await waitFor(() => {
      expect(read).toBe(f.IDS.notification);
    });
    expect(router.state.location.pathname).toBe(`/w/robot-lab/runs/${f.IDS.run2}`);
  });

  it("logs out", async () => {
    let loggedOut = false;
    server.use(
      http.post("/auth/logout", ({ response }) => {
        loggedOut = true;
        return response(204).empty();
      }),
    );
    const { router } = renderApp("/w/robot-lab/datasets");
    const user = userEvent.setup();
    server.use(http.get("/auth/me", () => problemResponse(401, "unauthenticated")));
    await user.click(await screen.findByRole("button", { name: "User menu" }));
    await user.click(await screen.findByRole("menuitem", { name: "Log out" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
    expect(loggedOut).toBe(true);
  });

  it("only allows in-app redirect targets", () => {
    expect(safeNext("/w/x/runs")).toBe("/w/x/runs");
    expect(safeNext("//evil.example")).toBe("/");
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext("/\\evil")).toBe("/");
    expect(safeNext(null)).toBe("/");
  });
});

describe("accessibility (axe, WCAG 2.1 A/AA rules runnable in jsdom)", () => {
  it.each([
    ["login", "/login", "Sign in"],
    ["datasets", "/w/robot-lab/datasets", "Datasets"],
    ["dataset detail", `/w/robot-lab/datasets/${f.IDS.dataset}`, "so101 pick and place"],
    ["runs", "/w/robot-lab/runs", "Training runs"],
    ["run detail", `/w/robot-lab/runs/${f.IDS.run}`, "act-picknplace"],
    ["models", `/w/robot-lab/models/${f.IDS.model}`, "act-picknplace"],
    ["account", "/account/tokens", "Account"],
    ["settings", "/w/robot-lab/settings/members", "Robot Lab settings"],
    ["admin", "/admin/users", "Administration"],
  ])("%s page has no axe violations", async (_name, url, heading) => {
    if (url === "/login") server.use(http.get("/auth/me", () => problemResponse(401, "unauthenticated")));
    renderApp(url);
    await screen.findByRole("heading", { name: new RegExp(heading) });
    await new Promise((r) => setTimeout(r, 50));
    expect(await axeViolations()).toEqual([]);
  });

  it("wizard policy & form steps have no axe violations", async () => {
    renderApp(`/w/robot-lab/runs/new?version=${f.IDS.version}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: /ACT/ }));
    expect(await axeViolations()).toEqual([]);
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await screen.findByText("Chunk size");
    expect(await axeViolations()).toEqual([]);
  });
});
