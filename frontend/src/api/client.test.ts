import { HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import * as f from "@/test/fixtures";
import { http, networkError, problemResponse, server } from "@/test/server";
import { api, ApiError, apiUrl, onUnauthenticated, readCookie, unwrap } from "./client";

describe("api client wrapper", () => {
  it("returns typed data from the generated client", async () => {
    const me = await unwrap(api.GET("/auth/me"));
    expect(me.user.email).toBe(f.user.email);
  });

  it("sends X-CSRF-Token from the hb_csrf cookie on unsafe methods only", async () => {
    document.cookie = "hb_csrf=csrf-token-value-0123456789abcdef0123; path=/";
    const seen: Record<string, string | null> = {};
    server.use(
      http.post("/auth/logout", ({ request, response }) => {
        seen.post = request.headers.get("X-CSRF-Token");
        return response(204).empty();
      }),
      http.get("/auth/me", ({ request }) => {
        seen.get = request.headers.get("X-CSRF-Token");
        return HttpResponse.json(f.me);
      }),
    );
    await unwrap(api.POST("/auth/logout"));
    await unwrap(api.GET("/auth/me"));
    expect(seen.post).toBe("csrf-token-value-0123456789abcdef0123");
    expect(seen.get).toBeNull();
    expect(readCookie("hb_csrf")).toBe("csrf-token-value-0123456789abcdef0123");
  });

  it("refreshes once on 401 token_expired and retries the request (body replayed)", async () => {
    let calls = 0;
    let refreshes = 0;
    const bodies: unknown[] = [];
    server.use(
      http.post("/auth/refresh", ({ response }) => {
        refreshes += 1;
        return response(204).empty();
      }),
      http.patch("/users/me", async ({ request }) => {
        calls += 1;
        bodies.push(await request.json());
        if (calls === 1) return problemResponse(401, "token_expired");
        return HttpResponse.json({ ...f.user, display_name: "New" });
      }),
    );
    const user = await unwrap(api.PATCH("/users/me", { body: { display_name: "New" } }));
    expect(user.display_name).toBe("New");
    expect(calls).toBe(2);
    expect(refreshes).toBe(1);
    expect(bodies).toEqual([{ display_name: "New" }, { display_name: "New" }]);
  });

  it("shares a single refresh between concurrent expired requests", async () => {
    let refreshes = 0;
    const seen = new Map<string, number>();
    server.use(
      http.post("/auth/refresh", async ({ response }) => {
        refreshes += 1;
        await new Promise((r) => setTimeout(r, 20));
        return response(204).empty();
      }),
      http.get("/datasets/{dataset_id}", ({ params }) => {
        const n = (seen.get(params.dataset_id) ?? 0) + 1;
        seen.set(params.dataset_id, n);
        return n === 1 ? problemResponse(401, "token_expired") : HttpResponse.json(f.dataset);
      }),
    );
    const ids = [f.IDS.dataset, f.IDS.version, f.IDS.job];
    const results = await Promise.all(
      ids.map((id) => unwrap(api.GET("/datasets/{dataset_id}", { params: { path: { dataset_id: id } } }))),
    );
    expect(results).toHaveLength(3);
    expect(refreshes).toBe(1);
  });

  it("emits unauthenticated when the refresh fails", async () => {
    const listener = vi.fn();
    const off = onUnauthenticated(listener);
    server.use(
      http.post("/auth/refresh", () => problemResponse(401, "refresh_reuse_detected")),
      http.get("/workspaces", () => problemResponse(401, "token_expired")),
    );
    await expect(unwrap(api.GET("/workspaces"))).rejects.toMatchObject({
      status: 401,
      code: "token_expired",
    });
    expect(listener).toHaveBeenCalledWith("session_expired");
    off();
  });

  it("maps problem+json to ApiError with code, request id and retry_after", async () => {
    server.use(http.post("/auth/login", () => problemResponse(423, "account_locked", { retry_after_s: 30 })));
    const err = await unwrap(api.POST("/auth/login", { body: { email: "a@b.co", password: "x" } })).catch(
      (e: unknown) => e,
    );
    expect(err).toBeInstanceOf(ApiError);
    const e = err as ApiError;
    expect(e.code).toBe("account_locked");
    expect(e.retryAfterS).toBe(30);
    expect(e.requestId).toBe("req-test");
  });

  it("maps network failures to network_error", async () => {
    server.use(http.get("/auth/config", () => networkError()));
    await expect(unwrap(api.GET("/auth/config"))).rejects.toMatchObject({ code: "network_error", status: 0 });
  });

  it("serialises array query params comma-separated (style=form, explode=false)", async () => {
    let query = "";
    server.use(
      http.get("/runs/compare", ({ request }) => {
        query = new URL(request.url).search;
        return HttpResponse.json({ runs: [], series: [], config_diff: [] });
      }),
    );
    await unwrap(
      api.GET("/runs/compare", { params: { query: { ids: [f.IDS.run, f.IDS.run2], keys: ["loss", "lr"] } } }),
    );
    expect(decodeURIComponent(query)).toContain(`ids=${f.IDS.run},${f.IDS.run2}`);
    expect(decodeURIComponent(query)).toContain("keys=loss,lr");
  });

  it("builds absolute same-origin URLs for media/download links", () => {
    expect(apiUrl("/models/x/download")).toBe(`${window.location.origin}/api/v1/models/x/download`);
    expect(apiUrl("/runs/x/logs", { download: true, skip: undefined })).toBe(
      `${window.location.origin}/api/v1/runs/x/logs?download=true`,
    );
  });
});
