/**
 * Hibiscus Email Worker (CONTRACT_NOTES §4.1). The API (provider `cloudflare`, A2) POSTs a signed
 * JSON request; this Worker verifies it and sends the mail through its `send_email` binding.
 * The sender address is fixed by configuration — callers choose only recipient and content.
 *
 *   POST /send   -> 202 {"status":"sent","message_id":...}
 *   GET  /health -> 200 {"status":"ok"}   (no secrets, no binding call)
 */

import { buildMime, MAX_BODY_BYTES, parseSendRequest, type SendRequest } from "./message";
import { verify } from "./signature";

/** Shape shared by the Email Service binding and the Email Routing `SendEmail` binding. */
export interface SendEmailBinding {
  send(message: unknown): Promise<unknown>;
}

export interface Env {
  EMAIL: SendEmailBinding;
  /** `wrangler secret put HIBISCUS_EMAIL_HMAC_SECRET` — same value as the API's HIBISCUS_EMAIL_WORKER_SECRET. */
  HIBISCUS_EMAIL_HMAC_SECRET: string;
  /** Optional, during rotation only: the previous secret is still accepted. */
  HIBISCUS_EMAIL_HMAC_SECRET_PREVIOUS?: string;
  MAIL_FROM: string;
  MAIL_FROM_NAME: string;
  /** "service" = Cloudflare Email Service structured send (default); "routing" = raw MIME EmailMessage. */
  SEND_MODE?: string;
}

type ErrorCode =
  | "not_found"
  | "method_not_allowed"
  | "unsupported_media_type"
  | "payload_too_large"
  | "unauthorized"
  | "bad_request"
  | "misconfigured"
  | "send_failed";

function json(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function problem(status: number, code: ErrorCode, detail?: string): Response {
  return json(status, detail === undefined ? { error: code } : { error: code, detail });
}

function log(level: "info" | "warn" | "error", msg: string, fields: Record<string, unknown>): void {
  // Never log secrets, signatures, bodies or full recipient addresses.
  console.log(JSON.stringify({ level, msg, service: "hibiscus-email-worker", ...fields }));
}

function recipientDomain(to: string): string {
  return to.slice(to.lastIndexOf("@") + 1);
}

export async function deliver(env: Env, req: SendRequest, now: Date): Promise<void> {
  const mode = env.SEND_MODE ?? "service";
  if (mode === "routing") {
    const domain = env.MAIL_FROM.slice(env.MAIL_FROM.lastIndexOf("@") + 1);
    const boundary = `lt-${crypto.randomUUID()}`;
    const raw = buildMime(env.MAIL_FROM, env.MAIL_FROM_NAME, req, domain, boundary, now);
    const { EmailMessage } = await import("cloudflare:email");
    await env.EMAIL.send(new EmailMessage(env.MAIL_FROM, req.to, raw));
    return;
  }
  const message: Record<string, unknown> = {
    to: req.to,
    from: { email: env.MAIL_FROM, name: env.MAIL_FROM_NAME },
    subject: req.subject,
    text: req.text,
    headers: { "Auto-Submitted": "auto-generated", "X-Hibiscus-Message-Id": req.message_id },
  };
  if (req.html !== undefined) message.html = req.html;
  if (req.reply_to !== undefined) message.replyTo = req.reply_to;
  await env.EMAIL.send(message);
}

export async function handle(request: Request, env: Env, nowMs: number = Date.now()): Promise<Response> {
  const url = new URL(request.url);
  if (url.pathname === "/health") {
    return request.method === "GET" ? json(200, { status: "ok" }) : problem(405, "method_not_allowed");
  }
  if (url.pathname !== "/send") {
    return problem(404, "not_found");
  }
  if (request.method !== "POST") {
    return problem(405, "method_not_allowed");
  }
  if (!env.HIBISCUS_EMAIL_HMAC_SECRET || env.HIBISCUS_EMAIL_HMAC_SECRET.length < 32 || !env.MAIL_FROM) {
    log("error", "worker misconfigured", { has_secret: Boolean(env.HIBISCUS_EMAIL_HMAC_SECRET) });
    return problem(500, "misconfigured");
  }
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    return problem(415, "unsupported_media_type");
  }
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > MAX_BODY_BYTES) {
    return problem(413, "payload_too_large");
  }
  const body = await request.text();
  if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) {
    return problem(413, "payload_too_large");
  }

  const nowSeconds = Math.floor(nowMs / 1000);
  const ts = request.headers.get("x-hibiscus-timestamp");
  const sig = request.headers.get("x-hibiscus-signature");
  let result = await verify(env.HIBISCUS_EMAIL_HMAC_SECRET, ts, sig, body, nowSeconds);
  if (!result.ok && result.reason === "bad_signature" && env.HIBISCUS_EMAIL_HMAC_SECRET_PREVIOUS) {
    result = await verify(env.HIBISCUS_EMAIL_HMAC_SECRET_PREVIOUS, ts, sig, body, nowSeconds);
  }
  if (!result.ok) {
    log("warn", "rejected request", { reason: result.reason });
    // One generic answer: do not tell an attacker which check failed.
    return problem(401, "unauthorized");
  }

  const parsed = parseSendRequest(body);
  if (!parsed.ok) {
    return problem(400, "bad_request", parsed.error);
  }
  const req = parsed.value;
  try {
    await deliver(env, req, new Date(nowMs));
  } catch (err) {
    log("error", "send failed", {
      message_id: req.message_id,
      to_domain: recipientDomain(req.to),
      error: err instanceof Error ? err.message : String(err),
    });
    return problem(502, "send_failed");
  }
  log("info", "sent", { message_id: req.message_id, to_domain: recipientDomain(req.to) });
  return json(202, { status: "sent", message_id: req.message_id });
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handle(request, env);
  },
} satisfies ExportedHandler<Env>;
