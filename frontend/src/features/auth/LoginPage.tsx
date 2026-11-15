import { zodResolver } from "@hookform/resolvers/zod";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { useAuthConfig, useLogin, useLoginSecondFactor } from "@/api/hooks/auth";
import { safeNext } from "@/app/guards";
import { ErrorAlert } from "@/components/common";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AuthLayout } from "./AuthLayout";
import { Turnstile } from "./Turnstile";

const loginSchema = z.object({
  email: z.string().trim().min(1, "validation.required").email("validation.email"),
  password: z.string().min(1, "validation.required"),
});
type LoginValues = z.infer<typeof loginSchema>;

const codeSchema = z.object({ code: z.string().trim() });
type CodeValues = z.infer<typeof codeSchema>;

function SecondFactor({ mfaToken, onDone }: { mfaToken: string; onDone: () => void }) {
  const { t } = useTranslation();
  const [useRecovery, setUseRecovery] = useState(false);
  const verify = useLoginSecondFactor();
  const form = useForm<CodeValues>({ resolver: zodResolver(codeSchema), defaultValues: { code: "" } });
  const onSubmit = form.handleSubmit(async ({ code }) => {
    if (!useRecovery && !/^[0-9]{6}$/.test(code)) {
      form.setError("code", { message: t("validation.totp") });
      return;
    }
    if (useRecovery && code.length < 6) {
      form.setError("code", { message: t("validation.required") });
      return;
    }
    await verify.mutateAsync(
      useRecovery ? { mfa_token: mfaToken, recovery_code: code } : { mfa_token: mfaToken, code },
    );
    onDone();
  });
  return (
    <form onSubmit={(e) => void onSubmit(e).catch(() => undefined)} className="space-y-4" noValidate>
      <p className="text-sm text-muted-foreground">
        {useRecovery ? t("auth.mfa.recovery_help") : t("auth.mfa.totp_help")}
      </p>
      <Field
        label={useRecovery ? t("auth.mfa.recovery_code") : t("auth.mfa.code")}
        error={form.formState.errors.code?.message}
      >
        <Input
          autoComplete="one-time-code"
          inputMode={useRecovery ? "text" : "numeric"}
          {...form.register("code")}
        />
      </Field>
      <ErrorAlert error={verify.error} />
      <Button type="submit" className="w-full" disabled={verify.isPending}>
        {verify.isPending ? <PxIcon name="spinner" className="px-spin" /> : null}
        {t("auth.mfa.verify")}
      </Button>
      <Button
        variant="link"
        className="w-full"
        onClick={() => {
          setUseRecovery((v) => !v);
          form.reset({ code: "" });
        }}
      >
        {useRecovery ? t("auth.mfa.use_totp") : t("auth.mfa.use_recovery")}
      </Button>
    </form>
  );
}

/** POST /auth/login (+ /auth/login/2fa). */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const config = useAuthConfig();
  const login = useLogin();
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [turnstileReset, setTurnstileReset] = useState(0);
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const siteKey = config.data?.turnstile_site_key ?? null;

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const res = await login.mutateAsync({
        email: values.email,
        password: values.password,
        ...(turnstileToken ? { turnstile_token: turnstileToken } : {}),
      });
      if (res.status === "mfa_required" && res.mfa_token) {
        setMfaToken(res.mfa_token);
        return;
      }
      navigate(res.mfa_enrollment_required ? "/account/security?enroll=1" : next, { replace: true });
    } catch (e) {
      if (siteKey) setTurnstileReset((n) => n + 1);
      if (e instanceof ApiError && e.code === "invalid_credentials") form.setValue("password", "");
    }
  });

  if (mfaToken) {
    return (
      <AuthLayout title={t("auth.mfa.title")}>
        <SecondFactor
          mfaToken={mfaToken}
          onDone={() => {
            navigate(next, { replace: true });
          }}
        />
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t("auth.login.title")} description={t("auth.login.description")}>
      <form onSubmit={(e) => void onSubmit(e)} className="space-y-4" noValidate>
        <Field
          label={t("auth.email")}
          required
          error={form.formState.errors.email?.message ? t(form.formState.errors.email.message) : undefined}
        >
          <Input type="email" autoComplete="username" {...form.register("email")} />
        </Field>
        <Field
          label={t("auth.password")}
          required
          error={
            form.formState.errors.password?.message ? t(form.formState.errors.password.message) : undefined
          }
        >
          <Input type="password" autoComplete="current-password" {...form.register("password")} />
        </Field>
        {siteKey ? (
          <Turnstile siteKey={siteKey} onToken={setTurnstileToken} resetSignal={turnstileReset} />
        ) : null}
        <ErrorAlert error={login.error} />
        <Button type="submit" className="w-full" disabled={login.isPending || (!!siteKey && !turnstileToken)}>
          {login.isPending ? <PxIcon name="spinner" className="px-spin" /> : null}
          {t("auth.login.submit")}
        </Button>
        <div className="text-center text-sm">
          <Link to="/forgot-password" className="text-primary underline-offset-4 hover:underline">
            {t("auth.login.forgot")}
          </Link>
        </div>
        <p className="text-center text-xs text-muted-foreground">{t("auth.login.invite_only")}</p>
      </form>
    </AuthLayout>
  );
}
