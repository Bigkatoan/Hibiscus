# ADR-0008: Public ingress through Cloudflare Tunnel only

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect), confirmed by owner (PLAN §10.1, §10.3)
- **Source:** PLAN.md §2, ADR-8; §3.1

## Context

Hibiscus must be reachable from the Internet for the team and remote collection machines. It runs on a
home GPU workstation whose IP must not be exposed and which cannot absorb DDoS. The domain is on
Cloudflare. Consequences of Cloudflare as the edge: request body limit **100 MB** (Free/Pro), idle
connections cut after ~**100 s** (handled in ADR-0010).

## Decision

- `cloudflared` runs as a container and makes **outbound-only** connections to Cloudflare. **No port
  is opened on the router**; no service binds a public interface.
- Origin services (API, SPA static server, internal reverse proxy if used) listen only on the internal
  Docker network / `127.0.0.1`. MinIO, Postgres, Redis, Grafana and Prometheus are never routed
  through the tunnel.
- Cloudflare edge config: WAF managed rules, rate-limiting rule on `/api/v1/auth/*`, Bot Fight Mode,
  **Turnstile** on login and forgot-password, optional **Cloudflare Access** in front of `/admin`
  (API verifies `Cf-Access-Jwt-Assertion` when enabled).
- Real client IP: the API trusts `CF-Connecting-IP` **only** when the immediate peer is the
  `cloudflared` container; otherwise it uses the socket peer.
- Edge configuration (tunnel ingress, WAF/rate-limit rules) is kept as code in `deploy/`
  (Terraform Cloudflare provider or API scripts) with a separate staging subdomain.
- Security headers set by the origin: CSP, HSTS, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `X-Content-Type-Options`; strict CORS (same origin).

## Consequences

### Positive
- Home IP hidden; DDoS/WAF handled by Cloudflare; no inbound firewall holes.
- TLS terminates at Cloudflare and is carried over the tunnel; no certificate management at origin.

### Negative
- Hard 100 MB body limit and ~100 s idle timeout shape upload and streaming design (ADR-0010).
- Dependency on Cloudflare availability; LAN access can bypass via an internal hostname for ops.

### Follow-ups agents must honor
- A8: `deploy/` compose never publishes ports of internal services; tunnel config and WAF rules as
  code; staging subdomain; runbook for rotating the tunnel token.
- A2: IP-trust logic in `app/core` with tests for spoofed `CF-Connecting-IP` from a non-tunnel peer.
- A11/A10 (M7): ZAP full scan through the real Cloudflare path on staging; prove the origin is not
  reachable directly.
- Every endpoint must respect the body limit (no request > 64 MiB by design).

## Rejected alternatives

- **Open router port + Caddy TLS at origin:** exposes the home IP, DDoS is our problem.
- **VPN-only (Tailscale) access:** owner decided on public Internet access for the team.

## Related

- ADR-0006 (auth, Turnstile, IP), ADR-0010 (upload/SSE constraints)
- `deploy/`, `docs/runbook/`, `docs/security/`
