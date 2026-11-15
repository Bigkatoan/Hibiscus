import { zodResolver } from "@hookform/resolvers/zod";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import {
  useAcceptInvite,
  useAuthConfig,
  useInvitePreview,
  useMe,
  useRegisterWithInvite,
} from "@/api/hooks/auth";
import { ErrorAlert, PageLoader } from "@/components/common";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { applyFieldErrors } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { isLanguage } from "@/lib/i18n";
import { AuthLayout, readLinkToken } from "./AuthLayout";
import { clearInviteToken, peekInviteToken, stashInviteToken } from "./inviteToken";
import { Turnstile } from "./Turnstile";

/**
 * Invite link landing page: getInvitePreview, then registerWithInvite (new account) or
 * acceptInvite (existing, logged-in account).
 */
export function AcceptInvitePage() {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const { token: pathToken } = useParams();
  const navigate = useNavigate();
  const urlToken = readLinkToken(location.search, location.hash, pathToken);
  // SEC-auth-04: the token lives in sessionStorage, never in the query. Read it once from the
  // link (#token=, or a legacy ?token= / path segment), then scrub the URL to a bare /invite.
  const [token] = useState<string | null>(() => {
    if (urlToken) {
      stashInviteToken(urlToken);
      return urlToken;
    }
    return peekInviteToken();
  });
  useEffect(() => {
    if (urlToken) navigate("/invite", { replace: true });
  }, [urlToken, navigate]);
  const preview = useInvitePreview(token);
  useEffect(() => {
    if (preview.isError) clearInviteToken();
  }, [preview.isError]);
  const me = useMe();
  const config = useAuthConfig();
  const register = useRegisterWithInvite();
  const accept = useAcceptInvite();
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const minLength = config.data?.password_min_length ?? 12;
  const schema = z
    .object({
      display_name: z.string().trim().min(1, "validation.required").max(100),
      password: z.string().min(minLength, "validation.password_min").max(256, "validation.password_max"),
      confirm: z.string(),
    })
    .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "validation.password_mismatch" });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { display_name: "", password: "", confirm: "" },
  });

  if (!token) {
    return (
      <AuthLayout title={t("auth.invite.title")}>
        <Alert variant="destructive">{t("errors.invite_invalid")}</Alert>
      </AuthLayout>
    );
  }
  if (preview.isPending || me.isPending) return <PageLoader />;
  if (preview.isError) {
    return (
      <AuthLayout title={t("auth.invite.title")}>
        <ErrorAlert error={preview.error} />
        <div className="mt-4 text-center text-sm">
          <Link to="/login" className="text-primary underline-offset-4 hover:underline">
            {t("auth.back_to_login")}
          </Link>
        </div>
      </AuthLayout>
    );
  }
  const inv = preview.data;
  const description = t("auth.invite.description", {
    workspace: inv.workspace_name,
    role: t(`role.${inv.role}`),
    inviter: inv.invited_by ?? "—",
    expires: formatDateTime(inv.expires_at, i18n.language),
  });

  if (inv.account_exists || me.data) {
    const loggedInAsOther = me.data && me.data.user.email.toLowerCase() !== inv.email.toLowerCase();
    return (
      <AuthLayout title={t("auth.invite.title")} description={description}>
        {!me.data ? (
          <div className="space-y-4">
            <p className="text-sm">{t("auth.invite.login_first", { email: inv.email })}</p>
            <Button asChild className="w-full">
              <Link to={`/login?next=${encodeURIComponent("/invite")}`}>{t("auth.login.submit")}</Link>
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {loggedInAsOther ? <Alert variant="warning">{t("errors.invite_email_mismatch")}</Alert> : null}
            <ErrorAlert error={accept.error} />
            <Button
              className="w-full"
              disabled={accept.isPending}
              onClick={() => {
                accept.mutate(token, {
                  onSuccess: (m) => {
                    clearInviteToken();
                    navigate(`/w/${m.workspace_slug}/datasets`, { replace: true });
                  },
                });
              }}
            >
              {accept.isPending ? <PxIcon name="spinner" className="px-spin" /> : null}
              {t("auth.invite.accept")}
            </Button>
          </div>
        )}
      </AuthLayout>
    );
  }

  const onSubmit = form.handleSubmit(async (v) => {
    try {
      const lang = i18n.language;
      await register.mutateAsync({
        invite_token: token,
        display_name: v.display_name,
        password: v.password,
        ...(isLanguage(lang) ? { locale: lang } : {}),
        ...(turnstileToken ? { turnstile_token: turnstileToken } : {}),
      });
      clearInviteToken();
      navigate("/", { replace: true });
    } catch (e) {
      applyFieldErrors(e, form.setError, ["display_name", "password"], t);
    }
  });
  const err = (m?: string) => (m ? t(m, { min: minLength }) : undefined);
  const siteKey = config.data?.turnstile_site_key ?? null;
  return (
    <AuthLayout title={t("auth.invite.title")} description={description}>
      <form onSubmit={(e) => void onSubmit(e)} className="space-y-4" noValidate>
        <Field label={t("auth.email")}>
          <Input value={inv.email} readOnly autoComplete="username" />
        </Field>
        <Field
          label={t("auth.display_name")}
          required
          error={err(form.formState.errors.display_name?.message)}
        >
          <Input autoComplete="name" {...form.register("display_name")} />
        </Field>
        <Field
          label={t("auth.password")}
          required
          description={t("auth.password_rules", { min: minLength })}
          error={err(form.formState.errors.password?.message)}
        >
          <Input type="password" autoComplete="new-password" {...form.register("password")} />
        </Field>
        <Field
          label={t("auth.confirm_password")}
          required
          error={err(form.formState.errors.confirm?.message)}
        >
          <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
        </Field>
        {siteKey ? <Turnstile siteKey={siteKey} onToken={setTurnstileToken} /> : null}
        <ErrorAlert error={register.error} />
        <Button
          type="submit"
          className="w-full"
          disabled={register.isPending || (!!siteKey && !turnstileToken)}
        >
          {register.isPending ? <PxIcon name="spinner" className="px-spin" /> : null}
          {t("auth.invite.create_account")}
        </Button>
      </form>
    </AuthLayout>
  );
}
