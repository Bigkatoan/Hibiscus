# 7. Team, tokens and administration

*Primary (Vietnamese) version: `../vi/07-team-quan-tri.md`.*

## 7.1 Members (owner, admin)

**Members › Invite member** (Admin / Member / Viewer). Invites are emailed through **Cloudflare
Email Service**; if email delivery is off (Administration › System › Email delivery says "Off"),
Hibiscus shows the **invite link** for you to send privately — every flow works without email.
Invites last 72 h, single use; **Resend** issues a new link. A workspace always keeps at least one
owner. Removing a member revokes their tokens for the workspace; their data stays.

## 7.2 Access tokens for machines

One token per machine, minimal permissions: read datasets · upload datasets (includes read) · read
runs · start/control runs (includes read) · download models. Preset **Collection machine** =
upload + runs + download; **Read only** for machines that only pull models. Avoid non-expiring
tokens; revoke immediately when a machine is lost.

## 7.3 Platform administration

Requires two-factor authentication (optionally Cloudflare Access in front).

* **Users**: disable/enable, unlock, grant/revoke platform admin (target must have 2FA), reset 2FA
  (only after verifying identity in person), sign out everywhere + revoke tokens, **create a
  password reset link** (when email is off; audited).
* **Workspaces**: create (you become owner).
* **Quotas**: workspace default and per-user overrides (concurrent runs, queued runs, GPU-h/month,
  storage, max upload).
* **GPUs**: *Drain* before maintenance, *Disable* (current run re-queued from its last
  checkpoint), *Enable*.
* **Audit log** and **System** (versions, storage, queue, worker heartbeats, email provider).

## 7.4 Notifications

Bell 🔔 for run/model/dataset events. **Account › Notification channels**: email, Discord, Telegram,
webhook, with **Send test message**. **Workspace settings › Notify all members when** for team-wide
notices.
