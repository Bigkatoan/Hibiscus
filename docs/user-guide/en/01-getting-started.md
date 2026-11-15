# 1. Getting started: account, security, workspace

*English version (secondary). The Vietnamese guide is primary: `../vi/01-bat-dau.md`.*

## 1.1 Nothing to install

Open **https://robot.example.com** in a current Chrome, Firefox, Edge or Safari, on desktop or
phone. Uploading datasets, training, reading metrics and downloading models all work in the
browser. Only the collection machine next to the robot needs the `hibiscus` CLI (chapter 3), and
even there the browser works too. Switch **Tiếng Việt / English** at the top; it is saved per account.

## 1.2 Invite-only accounts

The server is on the public internet, so there is no public sign-up.

1. A workspace owner or admin invites your email. If the server does not send email yet, they send
   you the **invite link** over a private channel.
2. Open the link (valid **72 hours**, **single use**) → name, password (at least **12
   characters**; passwords found in data breaches are rejected) → **Create account and join**.
3. Already have an account? Sign in first, open the link → **Accept invite**.

Expired or invalid link: ask the inviter to **Resend** (the old link stops working).

## 1.3 Sign-in and two-factor authentication

* Email + password, sometimes with a Cloudflare Turnstile "Security check".
* Repeated wrong passwords **lock the account temporarily**; wait or reset your password.
* Two-factor authentication (Aegis, Google Authenticator, 1Password…) is **mandatory** for owners,
  admins and platform admins, recommended for everyone (**Account › Security**). Store the
  **10 recovery codes** safely; each works once. Codes always wrong? Check the phone's clock sync.

## 1.4 Forgot password

**Forgot your password?** → email → single-use reset link. Resetting signs out every device. If
the page says email is not configured, ask the administrator for a reset link
(Administration › Users › Create password reset link).

## 1.5 Workspaces and roles

Datasets, runs and models belong to a **workspace**, not to a person.

| Role | Can |
|---|---|
| Owner | Everything, including deleting the workspace. 2FA required |
| Admin | Members, invites, roles, control every run, higher priority. 2FA required |
| Member | Upload datasets, start and control **own** runs, download models |
| Viewer | Read only |

Both GPUs are shared by **fair-share** (whoever used less GPU recently goes first). Default
quotas: **1 concurrent run per user**, 200 GPU-hours/month, 200 GiB per workspace, 50 GiB per
upload. See **Usage**.

## 1.6 Sessions

**Account › Security › Active sessions** lists signed-in devices; sign them out remotely. "Signed
out for safety" means your session was used from two places at once: sign in again and change
your password. Collection machines use **access tokens** (chapter 3), never your password.
