import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { onUnauthenticated } from "@/api/client";
import { useMe } from "@/api/hooks/auth";
import { qk } from "@/api/hooks/keys";
import { PageLoader } from "@/components/common";
import { stripSensitiveQuery } from "@/features/auth/inviteToken";
import { NotFoundPage } from "@/features/misc/NotFoundPage";
import { isLanguage, setLanguage } from "@/lib/i18n";
import { i18n } from "@/lib/i18n";

/** When a refresh fails anywhere, drop the cached principal => guards redirect to /login. */
export function SessionWatcher() {
  const qc = useQueryClient();
  useEffect(
    () =>
      onUnauthenticated(() => {
        qc.setQueryData(qk.me, null);
      }),
    [qc],
  );
  return null;
}

export const ENROLL_PATH = "/account/security";

/** Only allow safe in-app redirect targets (no protocol-relative or absolute URLs). */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  // Never redirect to a URL that carries a token in its query (SEC-auth-04).
  return stripSensitiveQuery(next);
}

export function RequireAuth() {
  const me = useMe();
  const location = useLocation();
  const locale = me.data?.user.locale;
  useEffect(() => {
    if (isLanguage(locale) && i18n.language !== locale) setLanguage(locale);
  }, [locale]);
  if (me.isPending) return <PageLoader />;
  if (!me.data) {
    const next = stripSensitiveQuery(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  if (me.data.mfa_enrollment_required && location.pathname !== ENROLL_PATH) {
    return <Navigate to={`${ENROLL_PATH}?enroll=1`} replace />;
  }
  return <Outlet />;
}

export function RequirePlatformAdmin() {
  const me = useMe();
  if (me.isPending) return <PageLoader />;
  if (!me.data?.user.is_platform_admin) return <NotFoundPage />;
  return <Outlet />;
}

/** Login & co. redirect away when a session already exists. */
export function GuestOnly() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <PageLoader />;
  if (me.data && !me.data.mfa_enrollment_required) {
    const next = new URLSearchParams(location.search).get("next");
    return <Navigate to={safeNext(next)} replace />;
  }
  return <Outlet />;
}
