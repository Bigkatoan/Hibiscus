import { zodResolver } from "@hookform/resolvers/zod";
import { PxIcon } from "@/hibiscus/PixelAnim";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";
import type { Schemas } from "@/api/client";
import {
  useAuthConfig,
  useChangePassword,
  useMe,
  useRegenerateRecoveryCodes,
  useTotpDisable,
  useTotpEnable,
  useTotpSetup,
} from "@/api/hooks/auth";
import { CopyButton, ErrorAlert } from "@/components/common";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { applyFieldErrors } from "@/lib/errors";

/**
 * One-time display of recovery codes. The user must tick "I saved them" before the list can be
 * dismissed (QC-e2e-06: the codes are only returned once by enable/regenerate).
 */
function RecoveryCodesList({
  codes,
  onDone,
  tokensRevoked,
}: {
  codes: string[];
  onDone: () => void;
  /** Set right after enableTotp: every PAT of the user was revoked (SEC-auth-01). */
  tokensRevoked?: number | null;
}) {
  const { t } = useTranslation();
  const [saved, setSaved] = useState(false);
  return (
    <div className="space-y-3" data-testid="recovery-codes">
      {tokensRevoked !== undefined && tokensRevoked !== null ? (
        <Alert variant="warning" data-testid="tokens-revoked">
          {tokensRevoked > 0
            ? t("security.tokens_revoked_count", { count: tokensRevoked })
            : t("security.tokens_revoked_none")}{" "}
          {t("security.tokens_revoked_recreate")}
        </Alert>
      ) : null}
      <Alert variant="warning">{t("security.recovery_codes_once")}</Alert>
      <ul
        className="grid grid-cols-2 gap-2 rounded bg-muted p-3 font-mono text-sm"
        aria-label={t("security.recovery_codes")}
      >
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-3">
        <CopyButton value={codes.join("\n")} />
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={saved}
            onChange={(e) => {
              setSaved(e.target.checked);
            }}
          />
          {t("security.recovery_codes_saved")}
        </label>
        <Button disabled={!saved} onClick={onDone}>
          {t("security.recovery_codes_done")}
        </Button>
      </div>
    </div>
  );
}

function QrImage({ uri }: { uri: string }) {
  const { t } = useTranslation();
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    QRCode.toDataURL(uri, { margin: 1, width: 192 })
      .then((url) => {
        if (alive) setSrc(url);
      })
      .catch(() => {
        if (alive) setSrc(null);
      });
    return () => {
      alive = false;
    };
  }, [uri]);
  return src ? (
    <img src={src} alt={t("security.qr_alt")} width={192} height={192} className="rounded bg-white p-1" />
  ) : null;
}

/** setupTotp -> enableTotp; the recovery codes are handed to the parent (it outlives this form). */
function EnableTotp({ onEnabled }: { onEnabled: (res: Schemas["RecoveryCodes"]) => void }) {
  const { t } = useTranslation();
  const setup = useTotpSetup();
  const enable = useTotpEnable();
  const [secret, setSecret] = useState<Schemas["TotpSetup"] | null>(null);
  const pwForm = useForm<{ password: string }>({ defaultValues: { password: "" } });
  const codeForm = useForm<{ code: string }>({ defaultValues: { code: "" } });

  if (!secret) {
    return (
      <form
        className="space-y-3"
        onSubmit={(e) =>
          void pwForm
            .handleSubmit(async ({ password }) => {
              setSecret(await setup.mutateAsync(password));
            })(e)
            .catch(() => undefined)
        }
      >
        <Field label={t("security.confirm_password")} required>
          <Input
            type="password"
            autoComplete="current-password"
            {...pwForm.register("password", { required: true })}
          />
        </Field>
        <ErrorAlert error={setup.error} />
        <Button type="submit" disabled={setup.isPending}>
          {setup.isPending ? <PxIcon name="spinner" className="px-spin" /> : null}
          {t("security.setup_2fa")}
        </Button>
      </form>
    );
  }
  return (
    <form
      className="space-y-4"
      onSubmit={(e) =>
        void codeForm
          .handleSubmit(async ({ code }) => {
            if (!/^[0-9]{6}$/.test(code)) {
              codeForm.setError("code", { message: t("validation.totp") });
              return;
            }
            // useTotpEnable refetches /auth/me (mfa_enabled -> true), which unmounts this form,
            // so the codes must live in SecurityPanel.
            const res = await enable.mutateAsync(code);
            onEnabled(res);
          })(e)
          .catch(() => undefined)
      }
    >
      <p className="text-sm">{t("security.scan_qr")}</p>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <QrImage uri={secret.otpauth_uri} />
        <div className="min-w-0 space-y-1 text-sm">
          <p className="text-muted-foreground">{t("security.manual_secret")}</p>
          <code className="block break-all rounded bg-muted p-2">{secret.secret}</code>
        </div>
      </div>
      <Field label={t("auth.mfa.code")} required error={codeForm.formState.errors.code?.message}>
        <Input inputMode="numeric" autoComplete="one-time-code" {...codeForm.register("code")} />
      </Field>
      <Alert variant="warning" data-testid="enable-revokes-tokens">
        {t("security.enable_revokes_tokens")}
      </Alert>
      <ErrorAlert error={enable.error} />
      <Button type="submit" disabled={enable.isPending}>
        {enable.isPending ? <PxIcon name="spinner" className="px-spin" /> : null}
        {t("security.enable_2fa")}
      </Button>
    </form>
  );
}

function ManageTotp() {
  const { t } = useTranslation();
  const disable = useTotpDisable();
  const regen = useRegenerateRecoveryCodes();
  const [codes, setCodes] = useState<string[] | null>(null);
  const regenForm = useForm<{ code: string }>({ defaultValues: { code: "" } });
  const disableForm = useForm<{ password: string; code: string }>({
    defaultValues: { password: "", code: "" },
  });
  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h3 className="font-extrabold text-base">{t("security.recovery_codes")}</h3>
        {codes ? (
          <RecoveryCodesList
            codes={codes}
            onDone={() => {
              setCodes(null);
            }}
          />
        ) : (
          <form
            className="flex flex-col gap-2 sm:flex-row sm:items-end"
            onSubmit={(e) =>
              void regenForm
                .handleSubmit(async ({ code }) => {
                  setCodes((await regen.mutateAsync(code)).recovery_codes);
                })(e)
                .catch(() => undefined)
            }
          >
            <Field label={t("auth.mfa.code")} className="sm:w-48">
              <Input inputMode="numeric" autoComplete="one-time-code" {...regenForm.register("code")} />
            </Field>
            <Button type="submit" variant="outline" disabled={regen.isPending}>
              {t("security.regenerate_codes")}
            </Button>
          </form>
        )}
        <ErrorAlert error={regen.error} />
      </section>
      <section className="space-y-3">
        <h3 className="font-extrabold text-base">{t("security.disable_2fa")}</h3>
        <form
          className="grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end"
          onSubmit={(e) =>
            void disableForm
              .handleSubmit((v) => disable.mutateAsync(v))(e)
              .catch(() => undefined)
          }
        >
          <Field label={t("security.confirm_password")}>
            <Input type="password" autoComplete="current-password" {...disableForm.register("password")} />
          </Field>
          <Field label={t("auth.mfa.code")}>
            <Input inputMode="numeric" autoComplete="one-time-code" {...disableForm.register("code")} />
          </Field>
          <Button type="submit" variant="destructive" disabled={disable.isPending}>
            {t("security.disable_2fa")}
          </Button>
        </form>
        <ErrorAlert error={disable.error} />
      </section>
    </div>
  );
}

function ChangePassword() {
  const { t } = useTranslation();
  const config = useAuthConfig();
  const change = useChangePassword();
  const min = config.data?.password_min_length ?? 12;
  const schema = z
    .object({
      current_password: z.string().min(1, "validation.required"),
      new_password: z.string().min(min, "validation.password_min").max(256, "validation.password_max"),
      confirm: z.string(),
    })
    .refine((v) => v.new_password === v.confirm, {
      path: ["confirm"],
      message: "validation.password_mismatch",
    });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { current_password: "", new_password: "", confirm: "" },
  });
  const err = (m?: string) => (m ? t(m, { min }) : undefined);
  return (
    <form
      className="max-w-md space-y-3"
      noValidate
      onSubmit={(e) =>
        void form.handleSubmit(async (v) => {
          try {
            await change.mutateAsync({ current_password: v.current_password, new_password: v.new_password });
            form.reset();
          } catch (err2) {
            applyFieldErrors(err2, form.setError, ["new_password", "current_password"], t);
          }
        })(e)
      }
    >
      <Field
        label={t("security.current_password")}
        required
        error={err(form.formState.errors.current_password?.message)}
      >
        <Input type="password" autoComplete="current-password" {...form.register("current_password")} />
      </Field>
      <Field
        label={t("auth.new_password")}
        required
        description={t("auth.password_rules", { min })}
        error={err(form.formState.errors.new_password?.message)}
      >
        <Input type="password" autoComplete="new-password" {...form.register("new_password")} />
      </Field>
      <Field label={t("auth.confirm_password")} required error={err(form.formState.errors.confirm?.message)}>
        <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
      </Field>
      <ErrorAlert error={change.error} />
      {change.isSuccess ? <Alert variant="success">{t("security.password_changed")}</Alert> : null}
      <Button type="submit" disabled={change.isPending}>
        {t("security.change_password")}
      </Button>
    </form>
  );
}

export function SecurityPanel() {
  const { t } = useTranslation();
  const me = useMe();
  const [params] = useSearchParams();
  const enrolling = params.get("enroll") === "1" || !!me.data?.mfa_enrollment_required;
  const enabled = !!me.data?.user.mfa_enabled;
  const [freshCodes, setFreshCodes] = useState<string[] | null>(null);
  // null: regenerated codes; a number: codes from enableTotp, which revoked that many PATs.
  const [tokensRevoked, setTokensRevoked] = useState<number | null>(null);
  return (
    <div className="space-y-6">
      {enrolling && !enabled ? <Alert variant="warning">{t("security.enrollment_required")}</Alert> : null}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PxIcon name="shield" />
            {t("security.two_factor")}
            {enabled ? (
              <Badge variant="success">{t("security.enabled")}</Badge>
            ) : (
              <Badge variant="outline">{t("security.disabled")}</Badge>
            )}
          </CardTitle>
          <CardDescription>{t("security.two_factor_help")}</CardDescription>
        </CardHeader>
        <CardContent>
          {freshCodes ? (
            <RecoveryCodesList
              codes={freshCodes}
              tokensRevoked={tokensRevoked}
              onDone={() => {
                setFreshCodes(null);
                setTokensRevoked(null);
              }}
            />
          ) : enabled ? (
            <ManageTotp />
          ) : (
            <EnableTotp
              onEnabled={(res) => {
                setTokensRevoked(res.api_tokens_revoked ?? 0);
                setFreshCodes(res.recovery_codes);
              }}
            />
          )}
        </CardContent>
      </Card>
      {!me.data?.mfa_enrollment_required ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("security.change_password")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ChangePassword />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
