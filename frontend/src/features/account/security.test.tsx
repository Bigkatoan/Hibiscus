import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, server } from "@/test/server";

const CODES = Array.from({ length: 10 }, (_, i) => `abcd${i}-efgh${i}`);

describe("2FA enrolment", () => {
  it("shows the recovery codes after enabling, even though /auth/me flips mfa_enabled (QC-e2e-06)", async () => {
    let enabled = false;
    server.use(
      http.get("/auth/me", () =>
        HttpResponse.json({ ...f.me, user: { ...f.me.user, mfa_enabled: enabled } }),
      ),
      http.post("/auth/2fa/totp/setup", () =>
        HttpResponse.json({
          secret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
          otpauth_uri: "otpauth://totp/Hibiscus:an@example.com?secret=JBSWY3DPEHPK3PXP&issuer=Hibiscus",
        }),
      ),
      http.post("/auth/2fa/totp/enable", () => {
        enabled = true;
        return HttpResponse.json({ recovery_codes: CODES });
      }),
    );
    renderApp("/account/security");
    const user = userEvent.setup();
    // The 2FA card comes first; the change-password card has its own "Current password".
    const [pw] = await screen.findAllByLabelText(/Current password/);
    await user.type(pw!, "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Set up 2FA" }));
    await user.type(await screen.findByLabelText(/6-digit code/), "123456");
    await user.click(screen.getByRole("button", { name: "Enable 2FA" }));

    const box = await screen.findByTestId("recovery-codes");
    // me was refetched: the badge says Enabled, and the codes are still on screen.
    await screen.findByText("Enabled");
    const list = within(box).getByRole("list", { name: "Recovery codes" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(CODES);

    // Acknowledgement required before the codes go away.
    const done = within(box).getByRole("button", { name: "Done" });
    expect(done).toBeDisabled();
    await user.click(within(box).getByRole("checkbox", { name: "I have saved the recovery codes" }));
    await user.click(done);
    await waitFor(() => {
      expect(screen.queryByTestId("recovery-codes")).toBeNull();
    });
    expect(screen.getByRole("button", { name: "Generate new codes" })).toBeInTheDocument();
  });

  it("says that enabling 2FA revokes every PAT and refreshes the token list (SEC-auth-01)", async () => {
    let enabled = false;
    let tokenListCalls = 0;
    server.use(
      http.get("/auth/me", () =>
        HttpResponse.json({ ...f.me, user: { ...f.me.user, mfa_enabled: enabled } }),
      ),
      http.get("/auth/tokens", () => {
        tokenListCalls += 1;
        return HttpResponse.json({ items: enabled ? [] : [f.apiToken] });
      }),
      http.post("/auth/2fa/totp/setup", () =>
        HttpResponse.json({
          secret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
          otpauth_uri: "otpauth://totp/Hibiscus:an@example.com?secret=JBSWY3DPEHPK3PXP&issuer=Hibiscus",
        }),
      ),
      http.post("/auth/2fa/totp/enable", () => {
        enabled = true;
        return HttpResponse.json({ recovery_codes: CODES, api_tokens_revoked: 3 });
      }),
    );
    const { client } = renderApp("/account/security");
    // Prime the token list as if the Tokens tab had been opened before.
    await client.fetchQuery({ queryKey: ["tokens"], queryFn: () => Promise.resolve([]) });
    const user = userEvent.setup();
    const [pw] = await screen.findAllByLabelText(/Current password/);
    await user.type(pw!, "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Set up 2FA" }));
    // The confirmation step always warns before enabling.
    expect(await screen.findByTestId("enable-revokes-tokens")).toHaveTextContent(
      "revokes all of your personal access tokens",
    );
    await user.type(await screen.findByLabelText(/6-digit code/), "123456");
    await user.click(screen.getByRole("button", { name: "Enable 2FA" }));
    const notice = await screen.findByTestId("tokens-revoked");
    expect(notice).toHaveTextContent("3 personal access token(s) were revoked");
    expect(notice).toHaveTextContent("Create new tokens");
    await waitFor(() => {
      expect(client.getQueryState(["tokens"])?.isInvalidated).toBe(true);
    });
    expect(tokenListCalls).toBe(0);
  });

  it("notes on the PAT dialog that owner/admin tokens need 2FA", async () => {
    renderApp("/account/tokens");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Create token" }));
    expect(await screen.findByTestId("token-admin-2fa-note")).toHaveTextContent(/owner or admin need 2FA/);
  });
});
