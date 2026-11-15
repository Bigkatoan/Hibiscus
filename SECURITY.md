# Security policy

Hibiscus is meant to be exposed to the Internet (it ships with 2FA, rate limits, an audit log and a
loopback-only port policy), so we take vulnerability reports seriously. Thank you for helping keep
Hibiscus users safe.

## Supported versions

| Version | Supported |
|---|---|
| `main` | ✅ security fixes land here first |
| latest `0.x` release | ✅ fixes are released as a patch version |
| older releases | ❌ please upgrade |

## Reporting a vulnerability

**Do not open a public issue, discussion or pull request for a security problem.**

Report it privately through GitHub's
[private vulnerability reporting](https://github.com/Bigkatoan/Hibiscus/security/advisories/new)
(*Security* tab → *Report a vulnerability*). Please include:

* the affected component (`backend`, `worker`, `cli`, `frontend`, `deploy`) and version or commit,
* a description of the issue and its impact,
* steps to reproduce or a proof of concept (against your own instance only),
* any suggested fix or mitigation.

What to expect:

| Step | Target |
|---|---|
| Acknowledgement | within 3 working days |
| Initial assessment and severity (CVSS v3.1) | within 7 days |
| Fix or mitigation for critical / high issues | within 30 days |
| Public advisory (GitHub Security Advisory, CVE when applicable) | when a fixed release is available |

We will keep you informed and, if you wish, credit you in the advisory. Please give us a reasonable
time to fix the issue before any public disclosure (coordinated disclosure, 90 days by default).

## Scope

In scope: the code in this repository and the default configuration in `deploy/` (Compose stack,
Caddy, images built from `deploy/docker/`).

Out of scope: vulnerabilities in LeRobot, PyTorch or other upstream dependencies (report them
upstream; tell us if Hibiscus is affected), self-inflicted misconfiguration (for example publishing
internal ports despite `deploy/scripts/check_compose.py`), denial of service through volumetric
traffic, and findings from automated scanners without a demonstrated impact.

## Safe harbour

Good-faith research that respects this policy, avoids privacy violations and data destruction, and
only targets instances you own will not lead to legal action from the maintainers.

## Hardening guidance for operators

* Keep the stack on loopback and reach it through a tunnel or reverse proxy with TLS.
* Generate every secret with `deploy/scripts/gen-secrets.sh`; never reuse the `CHANGE_ME` placeholders.
* Enforce 2FA for admins, scope personal access tokens to the minimum, and rotate them.
* Subscribe to *Watch → Custom → Security alerts* on this repository to hear about advisories.
* See [`docs/runbook/secrets.md`](docs/runbook/secrets.md) and [`docs/runbook/upgrade.md`](docs/runbook/upgrade.md).
