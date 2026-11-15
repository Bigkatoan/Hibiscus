import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import type { Schemas } from "@/api/client";
import {
  useCreateNotificationChannel,
  useDeleteHfToken,
  useDeleteNotificationChannel,
  useHfTokenStatus,
  useMe,
  useResendVerification,
  useRevokeOtherSessions,
  useRevokeSession,
  useSessions,
  useSetHfToken,
  useTestNotificationChannel,
  useNotificationChannels,
  useUpdateMe,
} from "@/api/hooks/auth";
import { ConfirmButton, ErrorAlert, PageHeader, PageLoader } from "@/components/common";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input, NativeSelect } from "@/components/ui/input";
import { Alert, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime } from "@/lib/format";
import { isLanguage, setLanguage } from "@/lib/i18n";
import { SecurityPanel } from "./SecurityPanel";
import { TokensPanel } from "./TokensPanel";

function ProfilePanel() {
  const { t } = useTranslation();
  const me = useMe();
  const update = useUpdateMe();
  const resend = useResendVerification();
  const user = me.data?.user;
  const form = useForm<{ display_name: string; locale: string }>({
    values: { display_name: user?.display_name ?? "", locale: user?.locale ?? "vi" },
  });
  if (!user) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("account.profile")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="max-w-md space-y-4"
          onSubmit={(e) =>
            void form
              .handleSubmit(async (v) => {
                const locale = isLanguage(v.locale) ? v.locale : undefined;
                await update.mutateAsync({ display_name: v.display_name, ...(locale ? { locale } : {}) });
                if (locale) setLanguage(locale);
              })(e)
              .catch(() => undefined)
          }
        >
          <Field label={t("auth.email")}>
            <Input value={user.email} readOnly />
          </Field>
          {!user.email_verified ? (
            <Alert variant="warning">
              <p>{t("account.email_unverified")}</p>
              <Button
                variant="link"
                className="h-auto p-0"
                onClick={() => resend.mutate()}
                disabled={resend.isPending || resend.isSuccess}
              >
                {resend.isSuccess ? t("account.verification_sent") : t("account.resend_verification")}
              </Button>
            </Alert>
          ) : null}
          <Field label={t("auth.display_name")} required>
            <Input
              autoComplete="name"
              {...form.register("display_name", { required: true, maxLength: 100 })}
            />
          </Field>
          <Field label={t("prefs.language")}>
            <NativeSelect {...form.register("locale")}>
              <option value="vi">Tiếng Việt</option>
              <option value="en">English</option>
            </NativeSelect>
          </Field>
          <ErrorAlert error={update.error} />
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? <PxIcon name="spinner" className="px-spin" /> : null}
            {t("common.save")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function SessionsPanel() {
  const { t, i18n } = useTranslation();
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const revokeOthers = useRevokeOtherSessions();
  if (sessions.isPending) return <PageLoader />;
  if (sessions.isError) return <ErrorAlert error={sessions.error} />;
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>{t("account.sessions")}</CardTitle>
        <ConfirmButton
          variant="outline"
          size="sm"
          destructive
          title={t("account.revoke_others_confirm")}
          confirmLabel={t("account.revoke_others")}
          onConfirm={() => revokeOthers.mutateAsync()}
        >
          {t("account.revoke_others")}
        </ConfirmButton>
      </CardHeader>
      <CardContent>
        <Table>
          <THead>
            <TR>
              <TH>{t("account.device")}</TH>
              <TH>{t("account.ip")}</TH>
              <TH>{t("account.last_used")}</TH>
              <TH>
                <span className="sr-only">{t("common.actions")}</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {sessions.data.items.map((s) => (
              <TR key={s.id}>
                <TD className="max-w-xs truncate" title={s.user_agent ?? ""}>
                  {s.user_agent ?? "—"}{" "}
                  {s.current ? <Badge variant="secondary">{t("account.this_device")}</Badge> : null}
                </TD>
                <TD>{s.ip ?? "—"}</TD>
                <TD>{formatDateTime(s.last_used_at, i18n.language)}</TD>
                <TD className="text-right">
                  {!s.current ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => revoke.mutate(s.id)}
                      aria-label={t("account.revoke_session")}
                    >
                      <PxIcon name="trash" />
                    </Button>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}

const CHANNEL_EVENTS: Schemas["NotificationChannelCreate"]["events"] = [
  "run.succeeded",
  "run.failed",
  "run.stalled",
  "model.ready",
  "dataset.ready",
  "dataset.invalid",
];

function IntegrationsPanel() {
  const { t } = useTranslation();
  const hf = useHfTokenStatus();
  const setHf = useSetHfToken();
  const delHf = useDeleteHfToken();
  const channels = useNotificationChannels();
  const createChannel = useCreateNotificationChannel();
  const deleteChannel = useDeleteNotificationChannel();
  const testChannel = useTestNotificationChannel();
  const [hfToken, setHfToken] = useState("");
  const chForm = useForm<{ kind: Schemas["NotificationChannelKind"]; target: string; events: string[] }>({
    defaultValues: { kind: "discord", target: "", events: ["run.succeeded", "run.failed", "run.stalled"] },
  });
  const events = chForm.watch("events");
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("account.hf_token")}</CardTitle>
          <CardDescription>{t("account.hf_token_help")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {hf.data?.present ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="success">{t("account.hf_token_set")}</Badge>
              {hf.data.hint ? <code>{hf.data.hint}</code> : null}
              <Button variant="outline" size="sm" onClick={() => delHf.mutate()}>
                {t("common.delete")}
              </Button>
            </div>
          ) : null}
          <form
            className="flex max-w-lg flex-col gap-2 sm:flex-row sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              if (hfToken.length >= 8)
                setHf.mutate(hfToken, {
                  onSuccess: () => {
                    setHfToken("");
                  },
                });
            }}
          >
            <Field label={t("account.hf_token_new")} className="flex-1">
              <Input
                type="password"
                autoComplete="off"
                value={hfToken}
                onChange={(e) => {
                  setHfToken(e.target.value);
                }}
              />
            </Field>
            <Button type="submit" disabled={setHf.isPending || hfToken.length < 8}>
              {t("common.save")}
            </Button>
          </form>
          <ErrorAlert error={setHf.error} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("account.channels")}</CardTitle>
          <CardDescription>{t("account.channels_help")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ul className="divide-y rounded border">
            {(channels.data?.items ?? []).map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-2 p-3 text-sm">
                <Badge variant="secondary">{t(`account.channel_kind.${c.kind}`)}</Badge>
                <code className="truncate">{c.target_hint}</code>
                <span className="text-muted-foreground">{c.events.join(", ")}</span>
                <div className="ml-auto flex gap-1">
                  <Button variant="outline" size="sm" onClick={() => testChannel.mutate(c.id)}>
                    {t("account.channel_test")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={t("common.delete")}
                    onClick={() => deleteChannel.mutate(c.id)}
                  >
                    <PxIcon name="trash" />
                  </Button>
                </div>
              </li>
            ))}
            {channels.data?.items.length === 0 ? (
              <li className="p-3 text-sm text-muted-foreground">{t("account.channels_empty")}</li>
            ) : null}
          </ul>
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={(e) =>
              void chForm
                .handleSubmit(async (v) => {
                  await createChannel.mutateAsync({
                    kind: v.kind,
                    target: v.target,
                    events: CHANNEL_EVENTS.filter((ev) => v.events.includes(ev)),
                  });
                  chForm.reset();
                })(e)
                .catch(() => undefined)
            }
          >
            <Field label={t("account.channel_kind_label")}>
              <NativeSelect {...chForm.register("kind")}>
                {(["discord", "telegram", "webhook", "email"] as const).map((k) => (
                  <option key={k} value={k}>
                    {t(`account.channel_kind.${k}`)}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label={t("account.channel_target")} description={t("account.channel_target_help")}>
              <Input autoComplete="off" {...chForm.register("target", { required: true })} />
            </Field>
            <fieldset className="sm:col-span-2">
              <legend className="mb-2 text-sm font-medium">{t("account.channel_events")}</legend>
              <div className="flex flex-wrap gap-4">
                {CHANNEL_EVENTS.map((ev) => (
                  <label key={ev} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={events.includes(ev)}
                      onChange={(e) => {
                        chForm.setValue(
                          "events",
                          e.target.checked ? [...events, ev] : events.filter((x) => x !== ev),
                        );
                      }}
                    />
                    {t(`notifications.event.${ev}`)}
                  </label>
                ))}
              </div>
            </fieldset>
            <ErrorAlert error={createChannel.error} className="sm:col-span-2" />
            <div>
              <Button type="submit" disabled={createChannel.isPending}>
                {t("account.channel_add")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

const TABS = ["profile", "security", "sessions", "tokens", "integrations"] as const;

export function AccountPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const fromPath = location.pathname.split("/")[2];
  const tab = TABS.find((x) => x === fromPath) ?? "profile";
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title={t("account.title")} />
      <Tabs
        value={tab}
        onValueChange={(v) => {
          navigate(v === "profile" ? "/account" : `/account/${v}`);
        }}
      >
        <TabsList>
          {TABS.map((x) => (
            <TabsTrigger key={x} value={x}>
              {t(`account.tab.${x}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="profile">
          <ProfilePanel />
        </TabsContent>
        <TabsContent value="security">
          <SecurityPanel />
        </TabsContent>
        <TabsContent value="sessions">
          <SessionsPanel />
        </TabsContent>
        <TabsContent value="tokens">
          <TokensPanel />
        </TabsContent>
        <TabsContent value="integrations">
          <IntegrationsPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
