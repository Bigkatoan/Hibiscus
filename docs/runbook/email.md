# Email (Cloudflare Email Service)

Decision (CONTRACT_NOTES §4.1, user 2026-11-15): outgoing mail goes through **Cloudflare Email
Service** via a small Worker that owns the `send_email` binding
(`deploy/cloudflare/email-worker/`, wire contract in its README). The API's `cloudflare` provider
signs each request with HMAC-SHA256 over `"<timestamp>.<body>"` (5-minute window). Providers
`smtp` and `none` remain for development and as fallback; with `none`, admins generate links
manually and every flow keeps working.

**Not yet verified:** that Email Service sending is enabled on the account. Until a test mail
arrives (step 4 below), run with `HIBISCUS_EMAIL_PROVIDER=none`.

## 1. Choose the sending domain

Use a subdomain dedicated to transactional mail so its reputation and DMARC policy are isolated,
e.g. `robot.example.com` (matches the app URL) → From `no-reply@robot.example.com`.
`MAIL_FROM` in `wrangler.toml` and `HIBISCUS_EMAIL_FROM` in `deploy/.env` must use it.

## 2. DNS records (Cloudflare DNS, zone example.com)

Onboard the domain in **Email → Email Service → Sending** (dashboard). Cloudflare shows the exact
records to create — use those values; the shapes are:

| Type | Name | Value (shape) | Purpose |
|---|---|---|---|
| TXT | `robot.example.com` | `v=spf1 include:_spf.mx.cloudflare.net ~all` | SPF: authorise Cloudflare to send for the domain. **One SPF record per name** — merge with any existing `include:` instead of adding a second record. |
| TXT | `<selector>._domainkey.robot.example.com` | `v=DKIM1; k=rsa; p=<public key from dashboard>` (or CNAME as shown) | DKIM signature verification |
| TXT | `_dmarc.robot.example.com` | `v=DMARC1; p=none; rua=mailto:<reports mailbox>; adkim=s; aspf=r; pct=100` | DMARC; start with `p=none` |
| MX (optional) | `robot.example.com` | as shown if bounce handling requires it | bounces |

After two weeks of clean DMARC aggregate reports (only Cloudflare sources, all aligned), raise
to `p=quarantine`, later `p=reject`.

Check:

```bash
dig +short TXT robot.example.com
dig +short TXT _dmarc.robot.example.com
dig +short TXT <selector>._domainkey.robot.example.com
```

Send a test (step 4) to a Gmail address and inspect *Show original*: `SPF: PASS`, `DKIM: PASS`,
`DMARC: PASS`.

## 3. Deploy the Worker

See `deploy/cloudflare/email-worker/README.md` (wrangler login, `wrangler secret put
HIBISCUS_EMAIL_HMAC_SECRET`, `wrangler deploy`). Then in `deploy/.env`:

```
HIBISCUS_EMAIL_PROVIDER=cloudflare
HIBISCUS_EMAIL_WORKER_URL=https://hibiscus-email.<account-subdomain>.workers.dev/send
HIBISCUS_EMAIL_WORKER_SECRET=<same secret>
HIBISCUS_EMAIL_FROM=Hibiscus <no-reply@robot.example.com>
```

`make restart`. The API container needs outbound HTTPS (see the egress quirk in
[install.md](install.md#2-known-host-quirk-no-egress-from-bridge-containers)).

## 4. Verify end to end

```bash
deploy/cloudflare/email-worker/scripts/send-test.sh you@example.com   # expects 202 {"status":"sent"}
npx wrangler tail hibiscus-email                                        # live Worker logs (no addresses logged)
```

Then trigger a real flow (password reset for a test user) and check the admin status page
(`/admin/status` → email provider status).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Worker returns 401 | clock skew > 5 min on the GPU box (`timedatectl`), or secrets differ between `.env` and the Worker |
| 502 `send_failed`, Worker log "destination address not verified" | the binding is an Email *Routing* binding or `SEND_MODE=routing`; onboard Email Service sending |
| 500 `misconfigured` | `HIBISCUS_EMAIL_HMAC_SECRET` missing or < 32 chars in the Worker |
| Mail in spam | SPF/DKIM not passing, or DMARC alignment broken (From domain ≠ DKIM `d=`) |
| API logs connection errors to workers.dev | container egress (install.md §2) |

Fallback at any time: `HIBISCUS_EMAIL_PROVIDER=none`, `make restart`.
