# Cloudflare edge

Configuration as code: `deploy/cloudflare/edge/edge.json` (desired state, no secrets) +
`deploy/cloudflare/edge/cf_edge.py` (stdlib-only client for the Cloudflare API, tested against a
local fake API in `deploy/tests/test_cf_edge.py`). It was **not** run against the real account
during the build phase (no token was handed to agents).

## What it manages

| Phase / setting | Rules (ref) | Plan |
|---|---|---|
| `http_request_firewall_custom` | `hibiscus_block_internal_paths` (block `/metrics`, `/readyz`), `hibiscus_block_methods` (only GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS), optional `hibiscus_geo_challenge` (`allowed_countries`) | all |
| `http_ratelimit` | `hibiscus_rl_auth`: POST `/api/v1/auth/*` 10 req / 10 s per IP+colo, block 10 s; `hibiscus_rl_api` (Pro+): 1200 req / 60 s per IP on `/api/*` except upload parts | Free allows 1 rule |
| `http_request_cache_settings` | `hibiscus_bypass_api_cache`: no caching for `/api/*` and `/healthz` | all |
| Managed WAF | Free Managed Ruleset (automatic on Free); Cloudflare Managed Ruleset deployed by `apply` on Pro+ | |
| Zone settings / Bot Fight Mode | **only if listed in `edge.json`** — they are zone-wide and affect other hostnames | |

Every rule is scoped to `http.host eq "robot.example.com"`. `apply` rewrites only rules whose
`ref` starts with `hibiscus_` and keeps every other rule in those phases (other sites on the zone).
On the Free plan the single rate-limit slot must be free, otherwise the API returns an error and
nothing is changed in that phase.

**Bot Fight Mode is deliberately not enabled** (`"bot_fight_mode": null`): on the Free plan it
cannot be bypassed for API clients and would challenge the `hibiscus` CLI and collect machines
(PAT requests). Turnstile on login/forgot-password + the auth rate limit cover the browser flows.
On Pro+ use Super Bot Fight Mode with a skip rule for `/api/v1/` + `Authorization: Bearer hbp_`.

## Run it

```bash
export CLOUDFLARE_API_TOKEN=...   # scoped token, revoke afterwards
export CF_ZONE_ID=...             # example.com zone id
export CF_ACCOUNT_ID=...          # only for turnstile-create / access-create
cd deploy
uv run python cloudflare/edge/cf_edge.py plan      # offline, prints payloads
uv run python cloudflare/edge/cf_edge.py diff      # what would change
uv run python cloudflare/edge/cf_edge.py apply     # asks for confirmation
```

Token permissions: Zone → WAF: Edit, Zone Settings: Edit (only if `zone_settings` used), Bot
Management: Edit (only if `bot_fight_mode` set); Account → Turnstile: Edit; Access: Apps and
Policies: Edit (optional).

## Turnstile

```bash
uv run python cloudflare/edge/cf_edge.py turnstile-create >> .env   # prints SITE_KEY + SECRET once
make restart
```

The SPA's CSP already allows `https://challenges.cloudflare.com` (script + frame).

## Cloudflare Access for /admin (optional, off by default — CONTRACT_NOTES §4.4)

Set `access.enabled=true` and `allowed_emails` in `edge.json`, then
`cf_edge.py access-create` → prints `HIBISCUS_CF_ACCESS_AUD`; set it and
`HIBISCUS_CF_ACCESS_TEAM_DOMAIN=<team>.cloudflareaccess.com` in `deploy/.env`, `make restart`.
The application covers `robot.example.com/admin` and `/api/v1/admin` (subpaths included).
Admins open `/admin` directly once per session so the `CF_Authorization` cookie is set before the
SPA calls `/api/v1/admin*`. App-level login + 2FA stay mandatory.

## Tunnel

Remotely managed; origin must be `http://localhost:18000` ([install.md](install.md#5-point-the-tunnel-at-hibiscus-user-action-dashboard-only)).
Recommended tunnel origin settings: *No TLS Verify* not needed (plain HTTP), *HTTP Host Header*
empty, keep-alive defaults. SSE needs nothing at the edge besides the `Cache-Control: no-cache`
the API sends; uploads are ≤ 64 MiB per part (edge limit 100 MB).
A staging hostname (ADR-0008) is a second Public Hostname on the same tunnel pointing at the
dev stack `http://localhost:18100`, plus a copy of `edge.json` with its hostname.
