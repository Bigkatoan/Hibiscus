/**
 * Request authentication shared with the API's `cloudflare` EmailSender (A2).
 *
 *   X-Hibiscus-Timestamp: <unix seconds>
 *   X-Hibiscus-Signature: v1=<lowercase hex HMAC-SHA256(secret, "<timestamp>.<raw body>")>
 *
 * The timestamp must be within ±MAX_SKEW_SECONDS of the Worker clock (5-minute replay window,
 * CONTRACT_NOTES §4.1). Comparison is constant-time.
 */

export const MAX_SKEW_SECONDS = 300;
export const SIGNATURE_VERSION = "v1";

const encoder = new TextEncoder();

export type VerifyResult =
  | { ok: true }
  | { ok: false; reason: "missing_headers" | "bad_timestamp" | "stale_timestamp" | "bad_signature" };

export async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return toHex(new Uint8Array(mac));
}

export function toHex(bytes: Uint8Array): string {
  let out = "";
  for (const b of bytes) {
    out += b.toString(16).padStart(2, "0");
  }
  return out;
}

/** Constant-time comparison of two ASCII strings (length leak only). */
export function timingSafeEqual(a: string, b: string): boolean {
  const ab = encoder.encode(a);
  const bb = encoder.encode(b);
  let diff = ab.length ^ bb.length;
  const n = Math.max(ab.length, bb.length);
  for (let i = 0; i < n; i++) {
    diff |= (ab[i] ?? 0) ^ (bb[i] ?? 0);
  }
  return diff === 0;
}

export async function sign(secret: string, timestamp: string, body: string): Promise<string> {
  return `${SIGNATURE_VERSION}=${await hmacHex(secret, `${timestamp}.${body}`)}`;
}

export async function verify(
  secret: string,
  timestampHeader: string | null,
  signatureHeader: string | null,
  body: string,
  nowSeconds: number,
): Promise<VerifyResult> {
  if (timestampHeader === null || signatureHeader === null) {
    return { ok: false, reason: "missing_headers" };
  }
  if (!/^\d{1,12}$/.test(timestampHeader)) {
    return { ok: false, reason: "bad_timestamp" };
  }
  const ts = Number(timestampHeader);
  if (Math.abs(nowSeconds - ts) > MAX_SKEW_SECONDS) {
    return { ok: false, reason: "stale_timestamp" };
  }
  const expected = await sign(secret, timestampHeader, body);
  // Several signatures may be sent during secret rotation: "v1=<new>,v1=<old>".
  const candidates = signatureHeader.split(",").map((s) => s.trim());
  let match = false;
  for (const candidate of candidates) {
    if (timingSafeEqual(candidate, expected)) {
      match = true;
    }
  }
  return match ? { ok: true } : { ok: false, reason: "bad_signature" };
}
