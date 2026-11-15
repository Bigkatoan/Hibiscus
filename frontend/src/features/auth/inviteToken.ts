/**
 * Invite token handling (SEC-auth-04).
 *
 * The token must never sit in a URL query: Caddy logs `uri` and the `Referer` header, and a
 * query string survives into both. E-mailed links use `/invite#token=…` (fragments are never
 * sent to the server). On landing, the token is moved into sessionStorage and the URL is
 * replaced by a bare `/invite`, so the "log in first" detour (`/login?next=%2Finvite`) and
 * every later Referer carry no secret. Legacy `/invite?token=…` and `/invite/:token` links
 * are accepted once and scrubbed the same way.
 */

export const INVITE_TOKEN_KEY = "hibiscus.invite.token";

export function stashInviteToken(token: string): void {
  try {
    sessionStorage.setItem(INVITE_TOKEN_KEY, token);
  } catch {
    /* storage unavailable: the token then only lives in this page's memory */
  }
}

export function peekInviteToken(): string | null {
  try {
    return sessionStorage.getItem(INVITE_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function clearInviteToken(): void {
  try {
    sessionStorage.removeItem(INVITE_TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

/** True when a path+query carries a token-like parameter (raw or percent-encoded). */
export function hasSensitiveQuery(url: string): boolean {
  return /[?&#](?:token|invite_token)=/i.test(url) || /(?:%3F|%26|%23)(?:token|invite_token)%3D/i.test(url);
}

/**
 * Drop the query and fragment from an in-app path when they carry a token. Used for `?next=`
 * so a redirect target can never re-introduce a token into a logged URL.
 */
export function stripSensitiveQuery(path: string): string {
  if (!hasSensitiveQuery(path)) return path;
  const cut = path.search(/[?#]|%3F|%23/i);
  const base = cut === -1 ? path : path.slice(0, cut);
  return base || "/";
}
