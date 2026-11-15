import { zodResolver } from "@hookform/resolvers/zod";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { useAuthConfig, useForgotPassword, useResetPassword, useVerifyEmail } from "@/api/hooks/auth";
import { ErrorAlert } from "@/components/common";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { applyFieldErrors } from "@/lib/errors";
import { AuthLayout, readLinkToken } from "./AuthLayout";
import { Turnstile } from "./Turnstile";

export function passwordSchema(minLength: number) {
  return z
    .object({
      password: z.string().min(minLength, "validation.password_min").max(256, "validation.password_max"),
      confirm: z.string(),
    })
    .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "validation.password_mismatch" });
}

/** POST /auth/password/forgot — always shows the same confirmation (no account enumeration). */
export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const config = useAuthConfig();
  const forgot = useForgotPassword();
  const [sent, setSent] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const schema = z.object({ email: z.string().trim().email("validation.email") });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });
  const siteKey = config.data?.turnstile_site_key ?? null;
  const onSubmit = form.handleSubmit(async ({ email }) => {
    await forgot.mutateAsync({ email, ...(turnstileToken ? { turnstile_token: turnstileToken } : {}) });
    setSent(true);
  });
  return (
    <AuthLayout title={t("auth.forgot.title")} description={t("auth.forgot.description")}>
      {sent ? (
        <Alert variant="success">
          <div className="flex gap-2">
            <PxIcon name="check" className="mt-0.5 shrink-0" />
            <p>
              {config.data?.email_delivery_enabled === false
                ? t("auth.forgot.sent_no_email")
                : t("auth.forgot.sent")}
            </p>
          </div>
        </Alert>
      ) : (
        <form onSubmit={(e) => void onSubmit(e).catch(() => undefined)} className="space-y-4" noValidate>
          <Field
            label={t("auth.email")}
            required
            error={form.formState.errors.email?.message ? t(form.formState.errors.email.message) : undefined}
          >
            <Input type="email" autoComplete="email" {...form.register("email")} />
          </Field>
          {siteKey ? <Turnstile siteKey={siteKey} onToken={setTurnstileToken} /> : null}
          <ErrorAlert error={forgot.error} />
          <Button
            type="submit"
            className="w-full"
            disabled={forgot.isPending || (!!siteKey && !turnstileToken)}
          >
            {forgot.isPending ? <PxIcon name="spinner" className="px-spin" /> : null}
            {t("auth.forgot.submit")}
          </Button>
        </form>
      )}
      <div className="mt-4 text-center text-sm">
        <Link to="/login" className="text-primary underline-offset-4 hover:underline">
          {t("auth.back_to_login")}
        </Link>
      </div>
    </AuthLayout>
  );
}

/** POST /auth/password/reset with the emailed (or admin-generated) token. */
export function ResetPasswordPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const token = readLinkToken(location.search, location.hash);
  const config = useAuthConfig();
  const reset = useResetPassword();
  const minLength = config.data?.password_min_length ?? 12;
  const schema = passwordSchema(minLength);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirm: "" },
  });
  const [done, setDone] = useState(false);
  const onSubmit = form.handleSubmit(async ({ password }) => {
    if (!token) return;
    try {
      await reset.mutateAsync({ token, new_password: password });
      setDone(true);
    } catch (e) {
      applyFieldErrors(e, form.setError, ["new_password"], t);
    }
  });
  const err = (m?: string) => (m ? t(m, { min: minLength }) : undefined);
  return (
    <AuthLayout title={t("auth.reset.title")}>
      {!token ? (
        <ErrorAlertKey k="errors.one_time_token_invalid" />
      ) : done ? (
        <div className="space-y-4">
          <Alert variant="success">{t("auth.reset.done")}</Alert>
          <Button className="w-full" onClick={() => navigate("/login")}>
            {t("auth.back_to_login")}
          </Button>
        </div>
      ) : (
        <form onSubmit={(e) => void onSubmit(e)} className="space-y-4" noValidate>
          <Field
            label={t("auth.new_password")}
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
          <ErrorAlert error={reset.error} />
          <Button type="submit" className="w-full" disabled={reset.isPending}>
            {reset.isPending ? <PxIcon name="spinner" className="px-spin" /> : null}
            {t("auth.reset.submit")}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}

function ErrorAlertKey({ k }: { k: string }) {
  const { t } = useTranslation();
  return <Alert variant="destructive">{t(k)}</Alert>;
}

/** POST /auth/email/verify — runs once on mount. */
export function VerifyEmailPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const token = readLinkToken(location.search, location.hash);
  const verify = useVerifyEmail();
  const started = useRef(false);
  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      verify.mutate(token);
    }
  }, [token, verify]);
  return (
    <AuthLayout title={t("auth.verify.title")}>
      {!token ? <ErrorAlertKey k="errors.one_time_token_invalid" /> : null}
      {verify.isPending ? <p role="status">{t("common.loading")}</p> : null}
      {verify.isSuccess ? <Alert variant="success">{t("auth.verify.done")}</Alert> : null}
      <ErrorAlert error={verify.error} />
      <div className="mt-4 text-center text-sm">
        <Link to="/" className="text-primary underline-offset-4 hover:underline">
          {t("auth.continue")}
        </Link>
      </div>
    </AuthLayout>
  );
}
