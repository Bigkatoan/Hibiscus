/** Validation of the JSON body sent by the API and construction of the outgoing message. */

export const MAX_BODY_BYTES = 256 * 1024;

export interface SendRequest {
  to: string;
  subject: string;
  text: string;
  html?: string;
  reply_to?: string;
  /** Caller-chosen id (≤ 128 chars) echoed in logs and the Message-ID header; never secret. */
  message_id: string;
}

export type ParseResult = { ok: true; value: SendRequest } | { ok: false; error: string };

/**
 * Wire schema v1, exactly what the API's CloudflareWorkerEmailSender (backend/app/core/email.py)
 * emits; pinned byte for byte by test/fixtures/api-send-requests.json, which both the backend
 * test suite (tests/contract/test_email_worker_contract.py) and test/worker.test.ts use
 * (SEC-infra-1).
 *
 * * `from` is accepted for compatibility and IGNORED: the sender is fixed by the Worker's
 *   MAIL_FROM / MAIL_FROM_NAME, so a caller can never choose the From address.
 * * `html` and `reply_to` may be JSON null, which means "absent" (Python None).
 */
const ALLOWED_KEYS = new Set(["to", "subject", "text", "html", "reply_to", "message_id", "from"]);
// Deliberately conservative: one mailbox, no display name, no comments, no quoted local parts.
const EMAIL_RE =
  /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/;
const MESSAGE_ID_RE = /^[A-Za-z0-9._:-]{1,128}$/;
// eslint-disable-next-line no-control-regex -- the point is to reject control characters
const HEADER_UNSAFE_RE = /[\r\n\u0000-\u001f\u007f]/;

export function isEmail(value: string): boolean {
  return value.length <= 254 && EMAIL_RE.test(value);
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function parseSendRequest(raw: string): ParseResult {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return { ok: false, error: "body is not valid JSON" };
  }
  if (!isRecord(data)) {
    return { ok: false, error: "body must be a JSON object" };
  }
  for (const key of Object.keys(data)) {
    if (!ALLOWED_KEYS.has(key)) {
      return { ok: false, error: `unknown field: ${key}` };
    }
  }
  const { to, subject, text, message_id: messageId, from } = data;
  const html = data.html === null ? undefined : data.html;
  const replyTo = data.reply_to === null ? undefined : data.reply_to;
  if (from !== undefined && from !== null && typeof from !== "string") {
    return { ok: false, error: "from must be a string (it is ignored)" };
  }
  if (typeof to !== "string" || !isEmail(to)) {
    return { ok: false, error: "to must be a single email address" };
  }
  if (typeof subject !== "string" || subject.length === 0 || subject.length > 200) {
    return { ok: false, error: "subject must be 1..200 characters" };
  }
  if (HEADER_UNSAFE_RE.test(subject)) {
    return { ok: false, error: "subject must not contain control characters" };
  }
  if (typeof text !== "string" || text.length === 0) {
    return { ok: false, error: "text is required" };
  }
  if (html !== undefined && typeof html !== "string") {
    return { ok: false, error: "html must be a string" };
  }
  if (replyTo !== undefined && (typeof replyTo !== "string" || !isEmail(replyTo))) {
    return { ok: false, error: "reply_to must be an email address" };
  }
  if (typeof messageId !== "string" || !MESSAGE_ID_RE.test(messageId)) {
    return { ok: false, error: "message_id must match [A-Za-z0-9._:-]{1,128}" };
  }
  const value: SendRequest = { to, subject, text, message_id: messageId };
  if (html !== undefined) value.html = html;
  if (replyTo !== undefined) value.reply_to = replyTo;
  return { ok: true, value };
}

/** RFC 2047 encoded-word for non-ASCII header values. */
export function encodeHeader(value: string): string {
  if (/^[\x20-\x7e]*$/.test(value)) return value;
  const bytes = new TextEncoder().encode(value);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return `=?UTF-8?B?${btoa(bin)}?=`;
}

function base64Lines(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  const b64 = btoa(bin);
  return (b64.match(/.{1,76}/g) ?? []).join("\r\n");
}

/**
 * Raw RFC 5322 message for the Email Routing style binding (`EmailMessage(from, to, raw)`).
 * `boundary` and `date` are parameters so tests are deterministic.
 */
export function buildMime(
  from: string,
  fromName: string,
  req: SendRequest,
  domain: string,
  boundary: string,
  date: Date,
): string {
  const headers = [
    `From: ${encodeHeader(fromName)} <${from}>`,
    `To: <${req.to}>`,
    `Subject: ${encodeHeader(req.subject)}`,
    `Date: ${date.toUTCString()}`,
    `Message-ID: <${req.message_id}@${domain}>`,
    "MIME-Version: 1.0",
    "Auto-Submitted: auto-generated",
  ];
  if (req.reply_to !== undefined) headers.push(`Reply-To: <${req.reply_to}>`);
  if (req.html === undefined) {
    headers.push("Content-Type: text/plain; charset=UTF-8", "Content-Transfer-Encoding: base64");
    return `${headers.join("\r\n")}\r\n\r\n${base64Lines(req.text)}\r\n`;
  }
  headers.push(`Content-Type: multipart/alternative; boundary="${boundary}"`);
  const parts = [
    `--${boundary}`,
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    base64Lines(req.text),
    `--${boundary}`,
    "Content-Type: text/html; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    base64Lines(req.html),
    `--${boundary}--`,
    "",
  ];
  return `${headers.join("\r\n")}\r\n\r\n${parts.join("\r\n")}`;
}
