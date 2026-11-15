# Hibiscus Email Worker

Cloudflare Worker that sends Hibiscus's transactional email (verification, password reset,
invites, run notifications) through a **Cloudflare Email Service** `send_email` binding
(CONTRACT_NOTES §4.1, user decision 2026-11-15). The API never holds Cloudflare credentials: it
POSTs an HMAC-signed JSON request to this Worker; the Worker verifies it and calls the binding.

```
API (EmailSender provider "cloudflare", A2)
   │  POST https://hibiscus-email.<subdomain>.workers.dev/send
   │  X-Hibiscus-Timestamp / X-Hibiscus-Signature
   ▼
Worker ── verify HMAC + 5-min window ── validate body ── env.EMAIL.send(...) ──► recipient
```

## Wire contract (the API client must implement exactly this)

|                        |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Method / path          | `POST /send` (`GET /health` → `{"status":"ok"}`)                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `Content-Type`         | `application/json` (body ≤ 256 KiB)                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `X-Hibiscus-Timestamp` | Unix time in **seconds**, decimal                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `X-Hibiscus-Signature` | `v1=` + lowercase hex `HMAC-SHA256(secret, "<timestamp>.<raw body bytes>")`. Several comma-separated values are accepted (rotation).                                                                                                                                                                                                                                                                                                                                                  |
| Window                 | `abs(now - timestamp) ≤ 300 s`, otherwise 401                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Body                   | `{"to": "<one address>", "subject": "1..200 chars, no CR/LF", "text": "...", "html"?: "...", "reply_to"?: "<address>", "message_id": "[A-Za-z0-9._:-]{1,128}", "from"?: "..."}` — `html` / `reply_to` may be `null` (= absent); `from` is accepted and ignored (the sender is always `MAIL_FROM`); other unknown fields are rejected. The exact API requests are pinned by `test/fixtures/api-send-requests.json`, shared with `backend/tests/contract/test_email_worker_contract.py` |
| Sender                 | fixed by the Worker (`MAIL_FROM`, `MAIL_FROM_NAME` in `wrangler.toml`); callers cannot set it                                                                                                                                                                                                                                                                                                                                                                                         |
| Success                | `202 {"status":"sent","message_id":"..."}`                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Errors                 | `401 {"error":"unauthorized"}` (any auth failure, deliberately indistinct), `400 bad_request` (+`detail`), `404`, `405`, `413`, `415`, `500 misconfigured`, `502 send_failed`                                                                                                                                                                                                                                                                                                         |

Python reference for the client (A2):

```python
ts = str(int(time.time()))
body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
sig = "v1=" + hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
httpx.post(url, content=body, headers={"Content-Type": "application/json",
           "X-Hibiscus-Timestamp": ts, "X-Hibiscus-Signature": sig}, timeout=10)
```

Retry on 502 / network errors with backoff (the Worker is stateless; `message_id` lets you
correlate duplicates in logs). Do not retry 400/401.

## Deploy

Prerequisites (one time, Cloudflare dashboard): the sending domain (`robot.example.com` or
the apex) is onboarded to **Email Service → Sending**, and its SPF/DKIM/DMARC records exist
(`docs/runbook/email.md`). Availability of Email Service on the account was **not verified**
when this was written; until it is, keep `HIBISCUS_EMAIL_PROVIDER=none` in `deploy/.env`
(admin-generated links keep every flow usable).

```bash
cd deploy/cloudflare/email-worker
docker run --rm -it -u $(id -u):$(id -g) -e HOME=/tmp -v "$PWD":/w -w /w node:22.12-bookworm sh
npm ci
npx wrangler login            # or CLOUDFLARE_API_TOKEN with "Workers Scripts:Edit"
openssl rand -hex 32          # -> the shared secret; put the SAME value into deploy/.env
npx wrangler secret put HIBISCUS_EMAIL_HMAC_SECRET
npx wrangler deploy
```

Then set in `deploy/.env` and restart the API:

```
HIBISCUS_EMAIL_PROVIDER=cloudflare
HIBISCUS_EMAIL_WORKER_URL=https://hibiscus-email.<subdomain>.workers.dev/send
HIBISCUS_EMAIL_WORKER_SECRET=<same hex secret>
```

Smoke test from the host (signs a real request; sends one mail):

```bash
deploy/cloudflare/email-worker/scripts/send-test.sh you@example.com
```

### Rotating the secret (zero downtime)

1. `wrangler secret put HIBISCUS_EMAIL_HMAC_SECRET_PREVIOUS` ← the **current** value.
2. `wrangler secret put HIBISCUS_EMAIL_HMAC_SECRET` ← the new value.
3. Update `HIBISCUS_EMAIL_WORKER_SECRET` in `deploy/.env`, `docker compose up -d api`.
4. `wrangler secret delete HIBISCUS_EMAIL_HMAC_SECRET_PREVIOUS`.

## Send modes

- `SEND_MODE = "service"` (default): structured `env.EMAIL.send({to, from: {email, name},
subject, text, html, replyTo, headers})` — the Email Service sending API.
- `SEND_MODE = "routing"`: builds an RFC 5322 MIME message and sends
  `new EmailMessage(from, to, raw)` (`cloudflare:email`). This is the older Email Routing
  binding, which can only deliver to **verified destination addresses** — useful only for
  testing with your own mailbox.

The exact structured-message shape of the Email Service binding should be re-checked against the
current Cloudflare docs at deployment time (the service was new when this was written); the
shape is isolated in `deliver()` in `src/index.ts`.

## Develop / test

```bash
docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v "$PWD":/w -w /w node:22.12-bookworm \
  sh -c 'npm ci && npm run check'     # tsc + eslint (strict-type-checked) + prettier + vitest (coverage) + wrangler dry-run
```

Security notes: the Worker logs only `message_id`, the recipient **domain** and failure reasons —
never addresses, bodies, signatures or secrets. It has no state, no KV and no outbound fetch.
