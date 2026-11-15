# ADR-0006: In-house authentication built on vetted libraries

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect)
- **Source:** PLAN.md §2, ADR-6; §3.1

## Context

Hibiscus is reachable from the public Internet (ADR-0008), so authentication targets OWASP ASVS L2.
Requirements: invite-only registration, email verification, password reset, TOTP 2FA with recovery
codes, workspace RBAC (ADR-0009), Personal Access Tokens for collection machines, session
management and an immutable audit log. A full IdP is heavy for a single host; `fastapi-users` is in
maintenance mode. We build the flows ourselves but never implement crypto primitives.

## Decision

- **Passwords:** argon2id via `argon2-cffi` (library defaults or stronger), min 12 chars, checked
  against an offline breached-password list. Lockout after 5 failures with increasing backoff; rate
  limits per IP and per user in Redis.
- **Access token:** JWT, **EdDSA (Ed25519)** via PyJWT, **15 min** lifetime, in httpOnly cookie
  `hb_access` (`HttpOnly; Secure; SameSite=Strict; Path=/api`). Claims: `sub`, `sid`, `mfa`, `iat`, `exp`, `iss`, `aud`.
- **Refresh token:** opaque, rotating, in httpOnly cookie `hb_refresh` (`Path=/api/v1/auth`), stored
  hashed in `sessions` with a family id. Presenting a rotated (already used) token = **reuse
  detection** → revoke the entire session family and audit it.
- **CSRF:** double-submit cookie `hb_csrf` (readable by JS) + header `X-CSRF-Token`, required on all
  unsafe methods (POST/PUT/PATCH/DELETE) authenticated by cookie.
- **PAT:** `Authorization: Bearer hbp_<8-char prefix>_<secret>`; scopes `datasets:read`, `datasets:write`,
  `runs:read`, `runs:write`, `models:read`; expiry; shown once; stored as **sha256** hash; revocable;
  bound to one workspace. PAT requests are exempt from CSRF (no cookies).
- **2FA:** TOTP via `pyotp` + **10 recovery codes** (hashed, single use). Mandatory for workspace
  `owner`/`admin` and for platform admins (`users.is_platform_admin`).
- **Bot protection:** Cloudflare Turnstile verified server-side on login and forgot-password.
- **Client IP:** taken from `CF-Connecting-IP` only when the request arrived via `cloudflared`;
  otherwise the socket peer address.
- Email via a pluggable `EmailSender`; without a provider, a platform admin can mint a reset link.
- Audit events: login (success/fail), 2FA changes, role changes, token create/revoke, dataset
  create/delete, run start/cancel, model download.

## Consequences

### Positive
- Full control over flows and UX; no extra service; libraries are well-reviewed.

### Negative
- We own the security of the flow logic; requires dedicated review (A11) and ≥95% test coverage.

### Follow-ups agents must honor
- A2: all of the above lives in `backend/app/auth`; other packages use only its dependency functions
  (`current_user`, `require_scope`, `require_role`). Coverage ≥ 95%.
- Never log passwords, tokens, TOTP secrets, recovery codes or cookie values.
- Constant-time comparisons for token hashes; generic error messages for login/reset (no user
  enumeration); error `code`s from the contract catalog.
- A11: independent review of auth against ASVS L2 before M1 is done.

## Rejected alternatives

- **Keycloak / other IdP:** heavy to operate on one machine. **fastapi-users:** maintenance mode.
- **Tokens in localStorage:** XSS-exfiltratable. **HS256 JWT:** shared-secret; EdDSA preferred.

## Related

- ADR-0008 (Cloudflare), ADR-0009 (workspaces/roles)
- `api/openapi.yaml` (`/auth/*`, security schemes), `docs/security/`
