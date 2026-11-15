import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import type { Schemas } from "@/api/client";
import { useMe } from "@/api/hooks/auth";
import {
  useDeleteWorkspace,
  useCreateInvite,
  useInvites,
  useMembers,
  useRemoveMember,
  useResendInvite,
  useRevokeInvite,
  useUpdateMemberRole,
  useUpdateWorkspace,
  useWorkspaceDetail,
  useWorkspaceUsage,
} from "@/api/hooks/workspaces";
import { ConfirmButton, CopyButton, ErrorAlert, KeyValue, PageHeader, PageLoader } from "@/components/common";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Alert, Progress, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TokensPanel } from "@/features/account/TokensPanel";
import { formatBytes, formatDateTime, formatNumber } from "@/lib/format";
import { roleAtLeast, useCan, useWorkspace, type WorkspaceRole } from "./context";

const ROLES: WorkspaceRole[] = ["owner", "admin", "member", "viewer"];

function MembersPanel() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const me = useMe();
  const canManage = useCan("admin");
  const members = useMembers(ws.workspace_id);
  const updateRole = useUpdateMemberRole(ws.workspace_id);
  const remove = useRemoveMember(ws.workspace_id);
  if (members.isPending) return <PageLoader />;
  if (members.isError) return <ErrorAlert error={members.error} />;
  return (
    <div className="space-y-3">
      <ErrorAlert error={updateRole.error} />
      <Table>
        <THead>
          <TR>
            <TH>{t("members.name")}</TH>
            <TH>{t("auth.email")}</TH>
            <TH>{t("members.role")}</TH>
            <TH>{t("members.two_factor")}</TH>
            <TH>{t("members.joined")}</TH>
            <TH>
              <span className="sr-only">{t("common.actions")}</span>
            </TH>
          </TR>
        </THead>
        <TBody>
          {members.data.items.map((m) => {
            const self = m.user.id === me.data?.user.id;
            // Only owners can grant/remove owner; admins manage member/viewer.
            const editable = canManage && !self && (ws.role === "owner" || m.role !== "owner");
            return (
              <TR key={m.user.id}>
                <TD className="font-medium">{m.user.display_name}</TD>
                <TD>{m.email}</TD>
                <TD>
                  {editable ? (
                    <NativeSelect
                      aria-label={t("members.role_for", { name: m.user.display_name })}
                      className="h-9 w-36"
                      value={m.role}
                      onChange={(e) => {
                        updateRole.mutate({ userId: m.user.id, role: e.target.value as WorkspaceRole });
                      }}
                    >
                      {ROLES.filter((r) => ws.role === "owner" || r !== "owner").map((r) => (
                        <option key={r} value={r}>
                          {t(`role.${r}`)}
                        </option>
                      ))}
                    </NativeSelect>
                  ) : (
                    <Badge variant="secondary">{t(`role.${m.role}`)}</Badge>
                  )}
                </TD>
                <TD>
                  {m.mfa_enabled ? (
                    <Badge variant="success">{t("security.enabled")}</Badge>
                  ) : (
                    <Badge variant="outline">{t("security.disabled")}</Badge>
                  )}
                </TD>
                <TD>{formatDateTime(m.joined_at, i18n.language)}</TD>
                <TD className="text-right">
                  {editable ? (
                    <ConfirmButton
                      variant="ghost"
                      size="sm"
                      destructive
                      aria-label={t("members.remove")}
                      title={t("members.remove_confirm", { name: m.user.display_name })}
                      confirmLabel={t("members.remove")}
                      onConfirm={() => remove.mutateAsync(m.user.id)}
                    >
                      <PxIcon name="trash" />
                    </ConfirmButton>
                  ) : null}
                </TD>
              </TR>
            );
          })}
        </TBody>
      </Table>
    </div>
  );
}

function InvitesPanel() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const canManage = useCan("admin");
  const invites = useInvites(ws.workspace_id, canManage);
  const create = useCreateInvite(ws.workspace_id);
  const revoke = useRevokeInvite(ws.workspace_id);
  const resend = useResendInvite(ws.workspace_id);
  const [lastLink, setLastLink] = useState<string | null>(null);
  const form = useForm<{ email: string; role: Schemas["InviteCreate"]["role"] }>({
    defaultValues: { email: "", role: "member" },
  });
  if (!canManage) return <Alert>{t("members.invites_admin_only")}</Alert>;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("members.invite")}</CardTitle>
          <CardDescription>{t("members.invite_help")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 sm:grid-cols-[1fr_10rem_auto] sm:items-end"
            onSubmit={(e) =>
              void form
                .handleSubmit(async (v) => {
                  const inv = await create.mutateAsync(v);
                  setLastLink(inv.accept_url ?? null);
                  form.reset({ email: "", role: v.role });
                })(e)
                .catch(() => undefined)
            }
          >
            <Field label={t("auth.email")} required>
              <Input type="email" autoComplete="off" {...form.register("email", { required: true })} />
            </Field>
            <Field label={t("members.role")}>
              <NativeSelect {...form.register("role")}>
                {(["admin", "member", "viewer"] as const).map((r) => (
                  <option key={r} value={r}>
                    {t(`role.${r}`)}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <PxIcon name="spinner" className="px-spin" /> : <PxIcon name="user_plus" />}
              {t("members.send_invite")}
            </Button>
          </form>
          <ErrorAlert error={create.error} className="mt-3" />
          {lastLink ? (
            <Alert className="mt-3">
              <p className="mb-2">{t("members.invite_link_manual")}</p>
              <code className="mb-2 block break-all text-xs">{lastLink}</code>
              <CopyButton value={lastLink} />
            </Alert>
          ) : null}
        </CardContent>
      </Card>
      {invites.isPending ? <PageLoader /> : null}
      <ErrorAlert error={invites.error ?? resend.error ?? revoke.error} />
      {invites.data ? (
        <Table>
          <THead>
            <TR>
              <TH>{t("auth.email")}</TH>
              <TH>{t("members.role")}</TH>
              <TH>{t("members.invite_status")}</TH>
              <TH>{t("members.expires")}</TH>
              <TH>
                <span className="sr-only">{t("common.actions")}</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {invites.data.items.map((inv) => (
              <TR key={inv.id}>
                <TD>{inv.email}</TD>
                <TD>{t(`role.${inv.role}`)}</TD>
                <TD>
                  <Badge variant={inv.status === "pending" ? "default" : "outline"}>
                    {t(`members.invite_state.${inv.status}`)}
                  </Badge>
                </TD>
                <TD>{formatDateTime(inv.expires_at, i18n.language)}</TD>
                <TD className="space-x-1 text-right">
                  {inv.status === "pending" || inv.status === "expired" ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={t("members.resend")}
                      onClick={() => {
                        resend.mutate(inv.id, {
                          onSuccess: (r) => {
                            setLastLink(r.accept_url ?? null);
                          },
                        });
                      }}
                    >
                      {inv.status === "expired" ? <PxIcon name="refresh" /> : <PxIcon name="mail" />}
                    </Button>
                  ) : null}
                  {inv.status === "pending" ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={t("members.revoke")}
                      onClick={() => revoke.mutate(inv.id)}
                    >
                      <PxIcon name="trash" />
                    </Button>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}
    </div>
  );
}

function GeneralPanel() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const canEdit = useCan("admin");
  const detail = useWorkspaceDetail(ws.workspace_id);
  const usage = useWorkspaceUsage(ws.workspace_id);
  const update = useUpdateWorkspace(ws.workspace_id);
  const form = useForm<{ name: string; heldout: number; gpu: string }>({
    values: {
      name: detail.data?.name ?? ws.workspace_name,
      heldout: Math.round((detail.data?.settings?.default_heldout_fraction ?? 0.1) * 100),
      gpu: detail.data?.settings?.default_gpu ?? "auto",
    },
  });
  const u = usage.data;
  const pct = (a: number, b: number) => (b > 0 ? Math.min(100, (a / b) * 100) : 0);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>{t("workspace.general")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) =>
              void form
                .handleSubmit((v) =>
                  update.mutateAsync({
                    name: v.name,
                    settings: {
                      ...(detail.data?.settings ?? {}),
                      default_heldout_fraction: Math.max(0, Math.min(50, Number(v.heldout))) / 100,
                      default_gpu: v.gpu,
                    },
                  }),
                )(e)
                .catch(() => undefined)
            }
          >
            <Field label={t("workspace.name")} required>
              <Input disabled={!canEdit} {...form.register("name", { required: true })} />
            </Field>
            <Field label={t("workspace.default_heldout")} description={t("workspace.default_heldout_help")}>
              <Input
                type="number"
                min={0}
                max={50}
                step={1}
                disabled={!canEdit}
                {...form.register("heldout")}
              />
            </Field>
            <Field label={t("workspace.default_gpu")}>
              <NativeSelect disabled={!canEdit} {...form.register("gpu")}>
                <option value="auto">{t("gpu.auto")}</option>
                <option value="cuda0">cuda0</option>
                <option value="cuda1">cuda1</option>
              </NativeSelect>
            </Field>
            <ErrorAlert error={update.error} />
            {canEdit ? (
              <Button type="submit" disabled={update.isPending}>
                {t("common.save")}
              </Button>
            ) : null}
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("workspace.usage")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {u ? (
            <>
              <div>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{t("workspace.storage")}</span>
                  <span>
                    {formatBytes(u.workspace.storage_bytes_used, i18n.language)} /{" "}
                    {formatBytes(u.workspace.limits.storage_bytes, i18n.language)}
                  </span>
                </div>
                <Progress
                  value={pct(u.workspace.storage_bytes_used, u.workspace.limits.storage_bytes)}
                  aria-label={t("workspace.storage")}
                />
              </div>
              <div>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{t("workspace.gpu_hours")}</span>
                  <span>
                    {formatNumber(u.workspace.gpu_hours_this_month, i18n.language, 3)} /{" "}
                    {formatNumber(u.workspace.limits.gpu_hours_per_month, i18n.language)}
                  </span>
                </div>
                <Progress
                  value={pct(u.workspace.gpu_hours_this_month, u.workspace.limits.gpu_hours_per_month)}
                  aria-label={t("workspace.gpu_hours")}
                />
              </div>
              <KeyValue
                items={[
                  [t("workspace.active_runs"), `${u.workspace.active_runs}`],
                  [t("workspace.queued_runs"), `${u.workspace.queued_runs}`],
                  [t("workspace.my_gpu_hours"), formatNumber(u.me.gpu_hours_this_month, i18n.language, 3)],
                  [t("workspace.fair_share"), formatNumber(u.me.fair_share_gpu_hours_7d, i18n.language, 3)],
                  [t("workspace.max_concurrent"), `${u.me.limits.max_concurrent_runs}`],
                  [t("workspace.max_upload"), formatBytes(u.me.limits.max_upload_bytes, i18n.language)],
                ]}
              />
            </>
          ) : (
            <ErrorAlert error={usage.error} />
          )}
        </CardContent>
      </Card>
      {ws.role === "owner" ? <DangerZone /> : null}
    </div>
  );
}

/** deleteWorkspace (owner only; 409 workspace_not_empty while runs are active). */
function DangerZone() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const navigate = useNavigate();
  const del = useDeleteWorkspace(ws.workspace_id);
  return (
    <Card className="border-destructive/50 lg:col-span-2">
      <CardHeader>
        <CardTitle>{t("workspace.danger_zone")}</CardTitle>
        <CardDescription>{t("workspace.delete_help")}</CardDescription>
      </CardHeader>
      <CardContent>
        <ConfirmButton
          variant="destructive"
          destructive
          title={t("workspace.delete_confirm", { name: ws.workspace_name })}
          description={t("workspace.delete_help")}
          confirmLabel={t("workspace.delete")}
          onConfirm={async () => {
            await del.mutateAsync();
            navigate("/");
          }}
        >
          <PxIcon name="trash" />
          {t("workspace.delete")}
        </ConfirmButton>
      </CardContent>
    </Card>
  );
}

const TABS = ["general", "members", "invites", "tokens"] as const;

export function WorkspaceSettingsPage() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const { tab: tabParam } = useParams();
  const navigate = useNavigate();
  const tab = TABS.find((x) => x === tabParam) ?? "general";
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title={t("workspace.settings_title", { name: ws.workspace_name })}
        description={t("workspace.your_role", { role: t(`role.${ws.role}`) })}
      />
      <Tabs
        value={tab}
        onValueChange={(v) => {
          navigate(`/w/${ws.workspace_slug}/settings/${v}`);
        }}
      >
        <TabsList>
          {TABS.filter((x) => x !== "invites" || roleAtLeast(ws.role, "admin")).map((x) => (
            <TabsTrigger key={x} value={x}>
              {t(`workspace.tab.${x}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="general">
          <GeneralPanel />
        </TabsContent>
        <TabsContent value="members">
          <MembersPanel />
        </TabsContent>
        <TabsContent value="invites">
          <InvitesPanel />
        </TabsContent>
        <TabsContent value="tokens">
          <TokensPanel workspaceId={ws.workspace_id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
