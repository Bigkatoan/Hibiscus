import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { safeNext } from "@/app/guards";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, problemResponse, server } from "@/test/server";
import { hasSensitiveQuery, INVITE_TOKEN_KEY, stripSensitiveQuery } from "./inviteToken";

function loggedOut() {
  let loggedIn = false;
  server.use(
    http.get("/auth/me", () =>
      loggedIn ? HttpResponse.json(f.me) : problemResponse(401, "unauthenticated"),
    ),
  );
  return {
    login: () => {
      loggedIn = true;
    },
  };
}

describe("auth flows", () => {
  it("redirects unauthenticated users to /login with ?next and back after login", async () => {
    const session = loggedOut();
    let body: unknown = null;
    server.use(
      http.post("/auth/login", async ({ request }) => {
        body = await request.json();
        session.login();
        return HttpResponse.json({ status: "ok", user: f.user });
      }),
    );
    const { router } = renderApp("/w/robot-lab/runs");
    await screen.findByRole("heading", { name: "Sign in" });
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent("/w/robot-lab/runs")}`);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Email/), "an@example.com");
    await user.type(screen.getByLabelText(/^Password/), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/w/robot-lab/runs");
    });
    expect(body).toEqual({ email: "an@example.com", password: "correct horse battery" });
    await screen.findByRole("heading", { name: "Training runs" });
  });

  it("shows a localised error for invalid credentials and validates the form", async () => {
    loggedOut();
    server.use(http.post("/auth/login", () => problemResponse(401, "invalid_credentials")));
    renderApp("/login");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findAllByText("This field is required.")).toHaveLength(2);
    await user.type(screen.getByLabelText(/Email/), "not-an-email");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText(/Email/));
    await user.type(screen.getByLabelText(/Email/), "an@example.com");
    await user.type(screen.getByLabelText(/^Password/), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Incorrect email or password.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/)).toHaveValue("");
  });

  it("completes the TOTP second factor, or a recovery code", async () => {
    const session = loggedOut();
    const second: unknown[] = [];
    server.use(
      http.post("/auth/login", () =>
        HttpResponse.json({ status: "mfa_required", mfa_token: "mfa-token-123" }),
      ),
      http.post("/auth/login/2fa", async ({ request }) => {
        second.push(await request.json());
        if (second.length === 1) return problemResponse(401, "mfa_invalid_code");
        session.login();
        return HttpResponse.json({ status: "ok", user: f.user });
      }),
    );
    const { router } = renderApp("/login");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/Email/), "an@example.com");
    await user.type(screen.getByLabelText(/^Password/), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("heading", { name: "Two-factor authentication" });
    await user.type(screen.getByLabelText("6-digit code"), "12");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText("Enter the 6-digit code.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("6-digit code"));
    await user.type(screen.getByLabelText("6-digit code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText("The code is incorrect.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Use a recovery code instead" }));
    await user.type(screen.getByLabelText("Recovery code"), "abcd-efgh-ijkl");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => {
      expect(router.state.location.pathname).not.toBe("/login");
    });
    expect(second).toEqual([
      { mfa_token: "mfa-token-123", code: "123456" },
      { mfa_token: "mfa-token-123", recovery_code: "abcd-efgh-ijkl" },
    ]);
  });

  it("forces 2FA enrolment when the role requires it", async () => {
    server.use(
      http.get("/auth/me", () =>
        HttpResponse.json({
          ...f.me,
          user: { ...f.user, mfa_enabled: false },
          mfa_enrollment_required: true,
        }),
      ),
    );
    const { router } = renderApp("/w/robot-lab/datasets");
    await screen.findByText("Your role requires two-factor authentication. Set it up to continue.");
    expect(router.state.location.pathname).toBe("/account/security");
  });

  it("forgot password always confirms (no account enumeration)", async () => {
    loggedOut();
    let sent: unknown = null;
    server.use(
      http.post("/auth/password/forgot", async ({ request, response }) => {
        sent = await request.json();
        return response(202).empty();
      }),
    );
    renderApp("/forgot-password");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/Email/), "nobody@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText(/If an account exists for this email/)).toBeInTheDocument();
    expect(sent).toEqual({ email: "nobody@example.com" });
  });

  it("resets the password with the token from the link and checks confirmation", async () => {
    loggedOut();
    let sent: unknown = null;
    server.use(
      http.post("/auth/password/reset", async ({ request, response }) => {
        sent = await request.json();
        return response(204).empty();
      }),
    );
    renderApp("/reset-password#token=reset-token-abc");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/^New password/), "a-long-enough-password");
    await user.type(screen.getByLabelText(/^Confirm password/), "a-different-password!");
    await user.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText(/^Confirm password/));
    await user.type(screen.getByLabelText(/^Confirm password/), "a-long-enough-password");
    await user.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByText(/Your password was changed/)).toBeInTheDocument();
    expect(sent).toEqual({ token: "reset-token-abc", new_password: "a-long-enough-password" });
  });

  it("verifies the email token on load", async () => {
    let token = "";
    server.use(
      http.post("/auth/email/verify", async ({ request, response }) => {
        token = (await request.json()).token;
        return response(204).empty();
      }),
    );
    renderApp("/verify-email?token=verify-me");
    expect(await screen.findByText("Your email address is verified.")).toBeInTheDocument();
    expect(token).toBe("verify-me");
  });

  it("registers a new account from an invite", async () => {
    const session = loggedOut();
    let body: Record<string, unknown> = {};
    let previewBody: Record<string, unknown> = {};
    server.use(
      http.post("/auth/invites/preview", async ({ request }) => {
        previewBody = await request.json();
        return HttpResponse.json(f.invitePreview);
      }),
      http.post("/auth/register-invite", async ({ request }) => {
        body = await request.json();
        session.login();
        return HttpResponse.json({ status: "ok", user: f.user }, { status: 201 });
      }),
    );
    const { router } = renderApp("/invite?token=invite-token-xyz");
    expect(await screen.findByText(/An Nguyen invited you to Robot Lab as Member/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Display name/), "Chi");
    await user.type(screen.getByLabelText(/^Password/), "short");
    await user.type(screen.getByLabelText(/^Confirm password/), "short");
    await user.click(screen.getByRole("button", { name: "Create account and join" }));
    expect(await screen.findByText("Use at least 12 characters.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText(/^Password/));
    await user.clear(screen.getByLabelText(/^Confirm password/));
    await user.type(screen.getByLabelText(/^Password/), "a-long-enough-password");
    await user.type(screen.getByLabelText(/^Confirm password/), "a-long-enough-password");
    await user.click(screen.getByRole("button", { name: "Create account and join" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/w/robot-lab/datasets");
    });
    // The invite token travels in the body, never in the API URL path (SEC-auth-04).
    expect(previewBody).toEqual({ token: "invite-token-xyz" });
    expect(body).toMatchObject({
      invite_token: "invite-token-xyz",
      display_name: "Chi",
      password: "a-long-enough-password",
      locale: "en",
    });
  });

  it("accepts an invite with the logged-in account", async () => {
    let acceptBody: Record<string, unknown> = {};
    server.use(
      http.post("/auth/invites/preview", () =>
        HttpResponse.json({ ...f.invitePreview, email: f.user.email, account_exists: true }),
      ),
      http.post("/auth/invites/accept", async ({ request }) => {
        acceptBody = await request.json();
        return HttpResponse.json(f.membership2);
      }),
    );
    const { router } = renderApp("/invite/invite-token-xyz");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Accept invitation" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/w/side-project/datasets");
    });
    expect(acceptBody).toEqual({ token: "invite-token-xyz" });
  });

  it("keeps the invite token out of every URL query across the log-in detour (SEC-auth-04)", async () => {
    const TOKEN = "invite-token-xyz";
    const session = loggedOut();
    const previewTokens: unknown[] = [];
    let acceptBody: Record<string, unknown> = {};
    server.use(
      http.post("/auth/invites/preview", async ({ request }) => {
        previewTokens.push(((await request.json()) as { token: string }).token);
        return HttpResponse.json({ ...f.invitePreview, email: f.user.email, account_exists: true });
      }),
      http.post("/auth/login", () => {
        session.login();
        return HttpResponse.json({ status: "ok", user: f.user });
      }),
      http.post("/auth/invites/accept", async ({ request }) => {
        acceptBody = await request.json();
        return HttpResponse.json(f.membership2);
      }),
    );
    const { router } = renderApp(`/invite#token=${TOKEN}`);
    const seen: string[] = [];
    const unsubscribe = router.subscribe((st) => {
      seen.push(`${st.location.pathname}${st.location.search}${st.location.hash}`);
    });
    const login = await screen.findByRole("link", { name: "Sign in" });
    // The fragment was moved to sessionStorage and scrubbed from the URL.
    expect(router.state.location.hash).toBe("");
    expect(window.sessionStorage.getItem(INVITE_TOKEN_KEY)).toBe(TOKEN);
    expect(login.getAttribute("href")).toBe(`/login?next=${encodeURIComponent("/invite")}`);
    const user = userEvent.setup();
    await user.click(login);
    await screen.findByRole("heading", { name: "Sign in" });
    await user.type(screen.getByLabelText(/Email/), "an@example.com");
    await user.type(screen.getByLabelText(/^Password/), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await user.click(await screen.findByRole("button", { name: "Accept invitation" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/w/side-project/datasets");
    });
    unsubscribe();
    expect(acceptBody).toEqual({ token: TOKEN });
    expect(previewTokens.every((t) => t === TOKEN)).toBe(true);
    // No location ever carried the token (raw or percent-encoded); storage is cleared after use.
    expect(seen.length).toBeGreaterThan(2);
    for (const url of seen) expect(url).not.toContain(TOKEN);
    expect(window.sessionStorage.getItem(INVITE_TOKEN_KEY)).toBeNull();
  });

  it.each([`/invite?token=legacy-tok`, `/invite/legacy-tok`])(
    "scrubs the legacy invite link %s to a bare /invite",
    async (url) => {
      loggedOut();
      let previewBody: Record<string, unknown> = {};
      server.use(
        http.post("/auth/invites/preview", async ({ request }) => {
          previewBody = await request.json();
          return HttpResponse.json(f.invitePreview);
        }),
      );
      const { router } = renderApp(url);
      expect(await screen.findByText(/An Nguyen invited you to Robot Lab as Member/)).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/invite");
      expect(router.state.location.search).toBe("");
      expect(previewBody).toEqual({ token: "legacy-tok" });
    },
  );

  it("never redirects to a ?next= target that carries a token in its query", () => {
    expect(safeNext("/invite?token=abc")).toBe("/invite");
    expect(safeNext("/invite%3Ftoken%3Dabc")).toBe("/invite");
    expect(safeNext("/w/robot-lab/runs?tab=config")).toBe("/w/robot-lab/runs?tab=config");
    expect(stripSensitiveQuery("/x?a=1&token=t#y")).toBe("/x");
    expect(hasSensitiveQuery("/login?next=%2Finvite%3Ftoken%3Dabc")).toBe(true);
  });

  it("shows an expired invite clearly", async () => {
    loggedOut();
    server.use(http.post("/auth/invites/preview", () => problemResponse(410, "invite_expired")));
    renderApp("/invite?token=old");
    expect(await screen.findByText("This invitation has expired. Ask for a new one.")).toBeInTheDocument();
  });
});
