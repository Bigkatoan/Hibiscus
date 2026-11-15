import { describe, expect, it, vi } from "vitest";

import { deliver, type Env, handle } from "../src/index";
import { buildMime, encodeHeader, isEmail, parseSendRequest } from "../src/message";
import { hmacHex, MAX_SKEW_SECONDS, sign, timingSafeEqual, verify } from "../src/signature";
// Exact requests the API's CloudflareWorkerEmailSender emits (generated and pinned by
// backend/tests/contract/test_email_worker_contract.py) — SEC-infra-1.
import apiRequests from "./fixtures/api-send-requests.json";

const SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef";
const NOW_MS = Date.UTC(2026, 10, 15, 9, 30, 0);
const NOW_S = Math.floor(NOW_MS / 1000);

function makeEnv(overrides: Partial<Env> = {}): Env & { sent: unknown[] } {
  const sent: unknown[] = [];
  return {
    EMAIL: {
      send: vi.fn((m: unknown) => {
        sent.push(m);
        return Promise.resolve(undefined);
      }),
    },
    HIBISCUS_EMAIL_HMAC_SECRET: SECRET,
    MAIL_FROM: "no-reply@robot.example.com",
    MAIL_FROM_NAME: "Hibiscus",
    sent,
    ...overrides,
  };
}

const validBody = {
  to: "alice@example.org",
  subject: "Xác thực email Hibiscus",
  text: "Mã: 123456",
  html: "<p>Mã: <b>123456</b></p>",
  message_id: "verify-0b9a3c",
};

async function signedRequest(
  body: string,
  opts: { ts?: number; secret?: string; signature?: string; contentType?: string; path?: string } = {},
): Promise<Request> {
  const ts = String(opts.ts ?? NOW_S);
  const signature = opts.signature ?? (await sign(opts.secret ?? SECRET, ts, body));
  return new Request(`https://email.example.workers.dev${opts.path ?? "/send"}`, {
    method: "POST",
    headers: {
      "content-type": opts.contentType ?? "application/json",
      "x-hibiscus-timestamp": ts,
      "x-hibiscus-signature": signature,
    },
    body,
  });
}

describe("signature", () => {
  it("computes HMAC-SHA256 per RFC 4231 (test case 2)", async () => {
    expect(await hmacHex("Jefe", "what do ya want for nothing?")).toBe(
      "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843",
    );
  });

  it("signs '<timestamp>.<body>' with the v1 prefix (cross-checked against Python hmac)", async () => {
    // python3 -c 'import hmac,hashlib;print(hmac.new(b"Jefe", b"1794738600.{}", hashlib.sha256).hexdigest())'
    expect(await sign("Jefe", "1794738600", "{}")).toBe(
      "v1=2d7967e43f628caf0c6cdbd159f1cab65c314f1ddc05941173ebd194820513cb",
    );
  });

  it("accepts within the window and rejects outside it", async () => {
    const body = "{}";
    const ok = await sign(SECRET, String(NOW_S - MAX_SKEW_SECONDS), body);
    expect(await verify(SECRET, String(NOW_S - MAX_SKEW_SECONDS), ok, body, NOW_S)).toEqual({ ok: true });
    const old = String(NOW_S - MAX_SKEW_SECONDS - 1);
    expect(await verify(SECRET, old, await sign(SECRET, old, body), body, NOW_S)).toEqual({
      ok: false,
      reason: "stale_timestamp",
    });
    const future = String(NOW_S + MAX_SKEW_SECONDS + 1);
    expect((await verify(SECRET, future, await sign(SECRET, future, body), body, NOW_S)).ok).toBe(false);
  });

  it("rejects tampering, malformed and missing headers", async () => {
    const body = '{"a":1}';
    const good = await sign(SECRET, String(NOW_S), body);
    expect((await verify(SECRET, String(NOW_S), good, '{"a":2}', NOW_S)).ok).toBe(false);
    expect((await verify(SECRET, String(NOW_S + 1), good, body, NOW_S)).ok).toBe(false);
    expect(await verify(SECRET, "12abc", good, body, NOW_S)).toEqual({ ok: false, reason: "bad_timestamp" });
    expect(await verify(SECRET, null, good, body, NOW_S)).toEqual({ ok: false, reason: "missing_headers" });
    expect(await verify(SECRET, String(NOW_S), null, body, NOW_S)).toEqual({
      ok: false,
      reason: "missing_headers",
    });
    expect((await verify(SECRET, String(NOW_S), good.toUpperCase(), body, NOW_S)).ok).toBe(false);
  });

  it("accepts any of several comma-separated signatures (rotation)", async () => {
    const body = "{}";
    const good = await sign(SECRET, String(NOW_S), body);
    const other = await sign("x".repeat(40), String(NOW_S), body);
    expect((await verify(SECRET, String(NOW_S), `${other}, ${good}`, body, NOW_S)).ok).toBe(true);
  });

  it("compares in constant time semantics", () => {
    expect(timingSafeEqual("abc", "abc")).toBe(true);
    expect(timingSafeEqual("abc", "abd")).toBe(false);
    expect(timingSafeEqual("abc", "abcd")).toBe(false);
    expect(timingSafeEqual("", "")).toBe(true);
  });
});

describe("request validation", () => {
  it("accepts the documented shape", () => {
    const r = parseSendRequest(JSON.stringify(validBody));
    expect(r.ok).toBe(true);
  });

  it.each([
    [{ ...validBody, to: "a@b.c, eve@evil.com" }, "to must be"],
    [{ ...validBody, to: "Alice <alice@example.org>" }, "to must be"],
    [{ ...validBody, subject: "hi\r\nBcc: eve@evil.com" }, "control characters"],
    [{ ...validBody, subject: "" }, "subject must be"],
    [{ ...validBody, text: "" }, "text is required"],
    [{ ...validBody, from: 5 }, "from must be a string"],
    [{ ...validBody, bcc: "eve@evil.com" }, "unknown field: bcc"],
    [{ ...validBody, message_id: "<x>" }, "message_id"],
    [{ ...validBody, reply_to: "nope" }, "reply_to"],
    [{ ...validBody, html: 5 }, "html must be"],
  ])("rejects %j", (body, message) => {
    const r = parseSendRequest(JSON.stringify(body));
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain(message);
  });

  it("treats null html / reply_to as absent and ignores the caller's from (fixed sender)", () => {
    const r = parseSendRequest(
      JSON.stringify({ ...validBody, from: "CEO <ceo@example.org>", html: null, reply_to: null }),
    );
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.value).toEqual({
      to: validBody.to,
      subject: validBody.subject,
      text: validBody.text,
      message_id: validBody.message_id,
    });
    expect("from" in r.value).toBe(false);
  });

  it("rejects non-objects and invalid JSON", () => {
    expect(parseSendRequest("[1]").ok).toBe(false);
    expect(parseSendRequest("{").ok).toBe(false);
  });

  it("validates addresses conservatively", () => {
    expect(isEmail("bob.smith+tag@sub.example.co")).toBe(true);
    expect(isEmail("bob@localhost")).toBe(false);
    expect(isEmail("a@-bad.com")).toBe(false);
    expect(isEmail(`${"x".repeat(65)}@example.com`)).toBe(false);
  });
});

describe("handler", () => {
  it("sends a valid signed request through the binding with the configured sender", async () => {
    const env = makeEnv();
    const body = JSON.stringify(validBody);
    const res = await handle(await signedRequest(body), env, NOW_MS);
    expect(res.status).toBe(202);
    expect(await res.json()).toEqual({ status: "sent", message_id: "verify-0b9a3c" });
    expect(env.sent).toHaveLength(1);
    expect(env.sent[0]).toMatchObject({
      to: "alice@example.org",
      from: { email: "no-reply@robot.example.com", name: "Hibiscus" },
      subject: validBody.subject,
      text: validBody.text,
      html: validBody.html,
    });
  });

  it("rejects a bad signature, a stale timestamp and a replay outside the window with 401", async () => {
    const env = makeEnv();
    const body = JSON.stringify(validBody);
    for (const req of [
      await signedRequest(body, { secret: "wrong-secret-wrong-secret-wrong-secret" }),
      await signedRequest(body, { ts: NOW_S - 301 }),
      await signedRequest(body, { signature: "v1=deadbeef" }),
    ]) {
      const res = await handle(req, env, NOW_MS);
      expect(res.status).toBe(401);
      expect(await res.json()).toEqual({ error: "unauthorized" });
    }
    expect(env.sent).toHaveLength(0);
  });

  it("accepts the previous secret during rotation", async () => {
    const env = makeEnv({
      HIBISCUS_EMAIL_HMAC_SECRET: "n".repeat(40),
      HIBISCUS_EMAIL_HMAC_SECRET_PREVIOUS: SECRET,
    });
    const res = await handle(await signedRequest(JSON.stringify(validBody)), env, NOW_MS);
    expect(res.status).toBe(202);
  });

  it("verifies the signature before parsing the body", async () => {
    const env = makeEnv();
    const res = await handle(await signedRequest("not json", { signature: "v1=00" }), env, NOW_MS);
    expect(res.status).toBe(401);
    const res2 = await handle(await signedRequest("not json"), env, NOW_MS);
    expect(res2.status).toBe(400);
  });

  it("enforces method, path, content type and size", async () => {
    const env = makeEnv();
    expect((await handle(new Request("https://w.dev/send"), env, NOW_MS)).status).toBe(405);
    expect((await handle(new Request("https://w.dev/other", { method: "POST" }), env, NOW_MS)).status).toBe(
      404,
    );
    const body = JSON.stringify(validBody);
    expect((await handle(await signedRequest(body, { contentType: "text/plain" }), env, NOW_MS)).status).toBe(
      415,
    );
    const big = JSON.stringify({ ...validBody, text: "x".repeat(300 * 1024) });
    expect((await handle(await signedRequest(big), env, NOW_MS)).status).toBe(413);
    const health = await handle(new Request("https://w.dev/health"), env, NOW_MS);
    expect(health.status).toBe(200);
  });

  it("refuses to run with a missing or short secret", async () => {
    const env = makeEnv({ HIBISCUS_EMAIL_HMAC_SECRET: "short" });
    const res = await handle(
      await signedRequest(JSON.stringify(validBody), { secret: "short" }),
      env,
      NOW_MS,
    );
    expect(res.status).toBe(500);
  });

  it("maps a binding failure to 502 without leaking details", async () => {
    const env = makeEnv({
      EMAIL: { send: () => Promise.reject(new Error("destination address not verified")) },
    });
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const res = await handle(await signedRequest(JSON.stringify(validBody)), env, NOW_MS);
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "send_failed" });
    const logged = log.mock.calls.map((c) => String(c[0])).join("\n");
    expect(logged).not.toContain("alice@example.org");
    expect(logged).not.toContain(SECRET);
    expect(logged).toContain("example.org");
    log.mockRestore();
  });

  it("builds a raw MIME message in routing mode", async () => {
    const sent: unknown[] = [];
    vi.doMock("cloudflare:email", () => ({
      EmailMessage: class {
        constructor(
          public from: string,
          public to: string,
          public raw: string,
        ) {}
      },
    }));
    const env = makeEnv({
      SEND_MODE: "routing",
      EMAIL: {
        send: (m: unknown) => {
          sent.push(m);
          return Promise.resolve(undefined);
        },
      },
    });
    const parsed = parseSendRequest(JSON.stringify(validBody));
    if (!parsed.ok) throw new Error("fixture invalid");
    await deliver(env, parsed.value, new Date(NOW_MS));
    expect(sent).toHaveLength(1);
    const msg = sent[0] as { from: string; to: string; raw: string };
    expect(msg.from).toBe("no-reply@robot.example.com");
    expect(msg.to).toBe("alice@example.org");
    expect(msg.raw).toContain("Message-ID: <verify-0b9a3c@robot.example.com>");
    vi.doUnmock("cloudflare:email");
  });
});

describe("API contract (shared fixture with backend/tests/contract)", () => {
  it.each(apiRequests.requests.map((r) => [r.name, r] as const))(
    "accepts the API's real request: %s",
    async (_name, fixture) => {
      const env = makeEnv({ HIBISCUS_EMAIL_HMAC_SECRET: apiRequests.secret });
      const req = await signedRequest(fixture.body, {
        ts: Number(fixture.timestamp),
        signature: fixture.signature,
      });
      const res = await handle(req, env, Number(fixture.timestamp) * 1000);
      expect(res.status).toBe(202);
      expect(env.sent).toHaveLength(1);
      const sent = env.sent[0] as Record<string, unknown>;
      expect(sent).toMatchObject({
        to: fixture.expect.to,
        subject: fixture.expect.subject,
        text: fixture.expect.text,
        // the From address is the Worker's own, never the API-supplied "from"
        from: { email: "no-reply@robot.example.com", name: "Hibiscus" },
      });
      if (fixture.expect.html === null) {
        expect("html" in sent).toBe(false);
      } else {
        expect(sent.html).toBe(fixture.expect.html);
      }
      expect("replyTo" in sent).toBe(false);
    },
  );

  it("still rejects a tampered API request", async () => {
    const fixture = apiRequests.requests[0];
    if (fixture === undefined) throw new Error("fixture empty");
    const env = makeEnv({ HIBISCUS_EMAIL_HMAC_SECRET: apiRequests.secret });
    const req = await signedRequest(fixture.body.replace("alice@", "eve@"), {
      ts: Number(fixture.timestamp),
      signature: fixture.signature,
    });
    expect((await handle(req, env, Number(fixture.timestamp) * 1000)).status).toBe(401);
  });
});

describe("mime", () => {
  const req = { to: "a@example.org", subject: "Đặt lại mật khẩu", text: "xin chào", message_id: "m1" };

  it("encodes non-ASCII headers and bodies", () => {
    expect(encodeHeader("plain")).toBe("plain");
    expect(encodeHeader("Đặt")).toMatch(/^=\?UTF-8\?B\?[A-Za-z0-9+/=]+\?=$/);
    const raw = buildMime("f@example.com", "Hibiscus", req, "example.com", "b1", new Date(NOW_MS));
    expect(raw).toContain("Subject: =?UTF-8?B?");
    expect(raw).toContain("Content-Type: text/plain; charset=UTF-8");
    expect(raw.split("\r\n\r\n")[1]?.trim()).toBe(
      btoa(String.fromCharCode(...new TextEncoder().encode("xin chào"))),
    );
    expect(raw).not.toMatch(/[^\r]\n/);
  });

  it("produces multipart/alternative when html is present", () => {
    const raw = buildMime(
      "f@example.com",
      "Hibiscus",
      { ...req, html: "<p>x</p>" },
      "example.com",
      "b1",
      new Date(NOW_MS),
    );
    expect(raw).toContain('multipart/alternative; boundary="b1"');
    expect(raw).toContain("--b1--");
    expect(raw).toContain("Content-Type: text/html; charset=UTF-8");
  });
});
