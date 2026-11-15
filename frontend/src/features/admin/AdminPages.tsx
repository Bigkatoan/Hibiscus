import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet } from "react-router-dom";
import type { Schemas } from "@/api/client";
import {
  useAdminResetLink,
  useAdminRevokeSessions,
  useAdminUpdateGpu,
  useAdminUpdateUser,
  useAdminUsers,
  useAuditEvents,
  useQuotas,
  useSystemStatus,
  useUpsertQuota,
  type AuditFilters,
} from "@/api/hooks/admin";
import { useGpus, useWorkspaces } from "@/api/hooks/workspaces";
import { CopyButton, ErrorAlert, KeyValue, LoadMore, PageHeader, PageLoader } from "@/components/common";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Alert, Switch, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { GpuCard } from "@/features/gpus/GpusPage";
import { CreateWorkspaceDialog } from "./CreateWorkspaceDialog";
import { formatBytes, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const SECTIONS = ["users", "audit", "quotas", "gpus", "system"] as const;

export function AdminLayout() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title={t("admin.title")}
        description={t("admin.description")}
        actions={<CreateWorkspaceDialog />}
      />
      <nav
        aria-label={t("admin.title")}
        className="mb-6 flex flex-wrap items-end gap-1 border-b-2 border-frame px-1 pt-1"
      >
        {SECTIONS.map((s) => (
          <NavLink
            key={s}
            to={`/admin/${s}`}
            className={({ isActive }) =>
              cn(
                "-mb-[2px] inline-flex h-9 items-center whitespace-nowrap border-2 border-frame bg-secondary px-3 font-extrabold text-base text-secondary-foreground hover:brightness-105",
                isActive && "h-10 border-b-card bg-card text-card-foreground",
              )
            }
          >
            {t(`admin.section.${s}`)}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}

function UserRow({ u }: { u: Schemas["AdminUser"] }) {
  const { t, i18n } = useTranslation();
  const [link, setLink] = useState<string | null>(null);
  const update = useAdminUpdateUser();
  const revoke = useAdminRevokeSessions();
  const reset = useAdminResetLink();
  const locked = !!u.locked_until && new Date(u.locked_until) > new Date();
  return (
    <TR>
      <TD>
        <div className="font-medium">{u.display_name}</div>
        <div className="text-xs text-muted-foreground">{u.email}</div>
        {link ? (
          <div className="mt-2 space-y-1">
            <code className="block max-w-xs break-all text-xs">{link}</code>
            <CopyButton value={link} />
          </div>
        ) : null}
        <ErrorAlert error={update.error ?? revoke.error ?? reset.error} className="mt-2" />
      </TD>
      <TD>
        <div className="flex flex-wrap gap-1">
          {u.is_platform_admin ? <Badge>{t("admin.platform_admin")}</Badge> : null}
          {!u.is_active ? <Badge variant="destructive">{t("admin.disabled")}</Badge> : null}
          {locked ? <Badge variant="warning">{t("admin.locked")}</Badge> : null}
          {u.mfa_enabled ? (
            <Badge variant="success">2FA</Badge>
          ) : (
            <Badge variant="outline">{t("admin.no_2fa")}</Badge>
          )}
        </div>
      </TD>
      <TD className="text-xs">
        {u.workspaces.map((w) => `${w.workspace_name} (${t(`role.${w.role}`)})`).join(", ") || "—"}
      </TD>
      <TD>{formatDateTime(u.last_login_at, i18n.language)}</TD>
      <TD>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-xs">
            <Switch
              checked={u.is_active}
              onCheckedChange={(c) => {
                update.mutate({ id: u.id, body: { is_active: c } });
              }}
              aria-label={t("admin.active_for", { name: u.display_name })}
            />
            {t("admin.active")}
          </label>
          {locked ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                update.mutate({ id: u.id, body: { unlock: true } });
              }}
            >
              {t("admin.unlock")}
            </Button>
          ) : null}
          {u.mfa_enabled ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                update.mutate({ id: u.id, body: { reset_mfa: true } });
              }}
            >
              {t("admin.reset_mfa")}
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("admin.revoke_sessions")}
            onClick={() => {
              revoke.mutate(u.id);
            }}
          >
            <PxIcon name="logout" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("admin.reset_link")}
            onClick={() => {
              reset.mutate(u.id, {
                onSuccess: (r) => {
                  setLink(r.url);
                },
              });
            }}
          >
            <PxIcon name="key" />
          </Button>
        </div>
      </TD>
    </TR>
  );
}

export function AdminUsersPage() {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const users = useAdminUsers(search);
  const items = users.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="space-y-4">
      <form
        role="search"
        className="flex max-w-md gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(q.trim());
        }}
      >
        <label htmlFor="admin-user-search" className="sr-only">
          {t("common.search")}
        </label>
        <Input
          id="admin-user-search"
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
          }}
          placeholder={t("admin.search_users")}
        />
        <Button type="submit" variant="outline" size="icon" aria-label={t("common.search")}>
          <PxIcon name="search" />
        </Button>
      </form>
      {users.isPending ? <PageLoader /> : null}
      <ErrorAlert error={users.error} />
      {items.length ? (
        <Table>
          <THead>
            <TR>
              <TH>{t("admin.user")}</TH>
              <TH>{t("admin.flags")}</TH>
              <TH>{t("admin.workspaces")}</TH>
              <TH>{t("admin.last_login")}</TH>
              <TH>{t("common.actions")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((u) => (
              <UserRow key={u.id} u={u} />
            ))}
          </TBody>
        </Table>
      ) : null}
      <LoadMore
        hasNextPage={users.hasNextPage}
        isFetchingNextPage={users.isFetchingNextPage}
        fetchNextPage={users.fetchNextPage}
      />
    </div>
  );
}

export function AdminAuditPage() {
  const { t, i18n } = useTranslation();
  const [filters, setFilters] = useState<AuditFilters>({});
  const form = useForm<{ action: string; since: string; until: string }>({
    defaultValues: { action: "", since: "", until: "" },
  });
  const events = useAuditEvents(filters);
  const items = events.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="space-y-4">
      <form
        className="grid gap-3 sm:grid-cols-4 sm:items-end"
        onSubmit={(e) =>
          void form.handleSubmit((v) => {
            setFilters({
              ...(v.action ? { action: v.action as Schemas["AuditAction"] } : {}),
              ...(v.since ? { since: new Date(v.since).toISOString() } : {}),
              ...(v.until ? { until: new Date(v.until).toISOString() } : {}),
            });
          })(e)
        }
      >
        <Field label={t("admin.action")}>
          <Input placeholder="auth.login" {...form.register("action")} />
        </Field>
        <Field label={t("admin.since")}>
          <Input type="datetime-local" {...form.register("since")} />
        </Field>
        <Field label={t("admin.until")}>
          <Input type="datetime-local" {...form.register("until")} />
        </Field>
        <Button type="submit" variant="outline">
          {t("common.apply")}
        </Button>
      </form>
      {events.isPending ? <PageLoader /> : null}
      <ErrorAlert error={events.error} />
      <Table>
        <THead>
          <TR>
            <TH>{t("admin.when")}</TH>
            <TH>{t("admin.actor")}</TH>
            <TH>{t("admin.action")}</TH>
            <TH>{t("admin.target")}</TH>
            <TH>{t("admin.outcome")}</TH>
            <TH>IP</TH>
          </TR>
        </THead>
        <TBody>
          {items.map((e) => (
            <TR key={e.id}>
              <TD className="whitespace-nowrap">{formatDateTime(e.created_at, i18n.language)}</TD>
              <TD>
                {e.actor?.display_name ?? (e.actor_token_id ? `PAT ${e.actor_token_id.slice(0, 8)}` : "—")}
              </TD>
              <TD>
                <code className="text-xs">{e.action}</code>
              </TD>
              <TD className="text-xs">
                {e.target_type ? `${e.target_type}:${(e.target_id ?? "").slice(0, 8)}` : "—"}
              </TD>
              <TD>
                <Badge
                  variant={
                    e.outcome === "success" ? "success" : e.outcome === "denied" ? "warning" : "destructive"
                  }
                >
                  {t(`admin.outcome_value.${e.outcome}`)}
                </Badge>
              </TD>
              <TD className="text-xs">{e.ip ?? "—"}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
      <LoadMore
        hasNextPage={events.hasNextPage}
        isFetchingNextPage={events.isFetchingNextPage}
        fetchNextPage={events.fetchNextPage}
      />
    </div>
  );
}

const GiB = 1024 ** 3;

function QuotaForm({ ws, quota }: { ws: string; quota: Schemas["Quota"] | undefined }) {
  const { t } = useTranslation();
  const upsert = useUpsertQuota(ws);
  const form = useForm<{
    user_id: string;
    max_concurrent_runs: number;
    max_queued_runs: number;
    gpu_hours_per_month: number;
    storage_gib: number;
    upload_gib: number;
  }>({
    values: {
      user_id: quota?.user_id ?? "",
      max_concurrent_runs: quota?.max_concurrent_runs ?? 1,
      max_queued_runs: quota?.max_queued_runs ?? 10,
      gpu_hours_per_month: quota?.gpu_hours_per_month ?? 200,
      storage_gib: Math.round((quota?.storage_bytes ?? 200 * GiB) / GiB),
      upload_gib: Math.round((quota?.max_upload_bytes ?? 50 * GiB) / GiB),
    },
  });
  return (
    <form
      className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6 lg:items-end"
      onSubmit={(e) =>
        void form
          .handleSubmit((v) =>
            upsert.mutateAsync({
              user_id: v.user_id.trim() || null,
              max_concurrent_runs: Number(v.max_concurrent_runs),
              max_queued_runs: Number(v.max_queued_runs),
              gpu_hours_per_month: Number(v.gpu_hours_per_month),
              storage_bytes: Math.round(Number(v.storage_gib) * GiB),
              max_upload_bytes: Math.round(Number(v.upload_gib) * GiB),
            }),
          )(e)
          .catch(() => undefined)
      }
    >
      <Field label={t("admin.quota_user")} description={t("admin.quota_user_help")}>
        <Input {...form.register("user_id")} />
      </Field>
      <Field label={t("workspace.max_concurrent")}>
        <Input type="number" min={0} {...form.register("max_concurrent_runs")} />
      </Field>
      <Field label={t("admin.max_queued")}>
        <Input type="number" min={0} {...form.register("max_queued_runs")} />
      </Field>
      <Field label={t("workspace.gpu_hours")}>
        <Input type="number" min={0} step="any" {...form.register("gpu_hours_per_month")} />
      </Field>
      <Field label={t("admin.storage_gib")}>
        <Input type="number" min={0} {...form.register("storage_gib")} />
      </Field>
      <Field label={t("admin.upload_gib")}>
        <Input type="number" min={0} {...form.register("upload_gib")} />
      </Field>
      <ErrorAlert error={upsert.error} className="sm:col-span-3 lg:col-span-6" />
      <div>
        <Button type="submit" disabled={upsert.isPending}>
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}

export function AdminQuotasPage() {
  const { t, i18n } = useTranslation();
  const workspaces = useWorkspaces();
  const [ws, setWs] = useState("");
  const selected = ws !== "" ? ws : (workspaces.data?.items[0]?.id ?? "");
  const quotas = useQuotas(selected);
  const def = quotas.data?.items.find((q) => !q.user_id);
  return (
    <div className="space-y-4">
      <Alert>{t("admin.quotas_scope")}</Alert>
      <Field label={t("admin.workspace")} className="max-w-sm">
        <NativeSelect
          value={selected}
          onChange={(e) => {
            setWs(e.target.value);
          }}
        >
          {(workspaces.data?.items ?? []).map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <ErrorAlert error={quotas.error} />
      {selected ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("admin.quota_edit")}</CardTitle>
          </CardHeader>
          <CardContent>
            <QuotaForm ws={selected} quota={def} />
          </CardContent>
        </Card>
      ) : null}
      {quotas.data ? (
        <Table>
          <THead>
            <TR>
              <TH>{t("admin.quota_user")}</TH>
              <TH>{t("workspace.max_concurrent")}</TH>
              <TH>{t("admin.max_queued")}</TH>
              <TH>{t("workspace.gpu_hours")}</TH>
              <TH>{t("workspace.storage")}</TH>
              <TH>{t("workspace.max_upload")}</TH>
            </TR>
          </THead>
          <TBody>
            {quotas.data.items.map((q) => (
              <TR key={q.id}>
                <TD>
                  {q.user_id ? (
                    <code className="text-xs">{q.user_id.slice(0, 8)}</code>
                  ) : (
                    t("admin.quota_default")
                  )}
                </TD>
                <TD>{q.max_concurrent_runs}</TD>
                <TD>{q.max_queued_runs}</TD>
                <TD>{q.gpu_hours_per_month}</TD>
                <TD>{formatBytes(q.storage_bytes, i18n.language)}</TD>
                <TD>{formatBytes(q.max_upload_bytes, i18n.language)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}
    </div>
  );
}

export function AdminGpusPage() {
  const { t } = useTranslation();
  const gpus = useGpus(5000);
  const update = useAdminUpdateGpu();
  return (
    <div className="space-y-4">
      <ErrorAlert error={gpus.error ?? update.error} />
      <div className="grid gap-4 md:grid-cols-2">
        {gpus.data?.items.map((g) => (
          <GpuCard key={g.id} gpu={g}>
            <div className="flex flex-wrap gap-2 pt-2">
              {(["online", "draining", "disabled"] as const).map((s) => (
                <Button
                  key={s}
                  variant={g.status === s ? "default" : "outline"}
                  size="sm"
                  disabled={g.status === s || update.isPending}
                  onClick={() => {
                    update.mutate({ id: g.id, status: s });
                  }}
                >
                  {t(`gpu.set_status.${s}`)}
                </Button>
              ))}
            </div>
          </GpuCard>
        ))}
      </div>
    </div>
  );
}

export function AdminSystemPage() {
  const { t, i18n } = useTranslation();
  const sys = useSystemStatus();
  if (sys.isPending) return <PageLoader />;
  if (sys.isError) return <ErrorAlert error={sys.error} />;
  const s = sys.data;
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("admin.versions")}</CardTitle>
        </CardHeader>
        <CardContent>
          <KeyValue
            items={[
              ["Hibiscus", s.hibiscus_version],
              ["LeRobot", s.lerobot_version],
              ["API", s.api_version],
              [t("admin.queue_depth"), `${s.queue_depth}`],
              [t("admin.disk_free"), formatBytes(s.storage.disk_free_bytes ?? null, i18n.language)],
              [
                t("admin.email"),
                `${t(`admin.email_provider.${s.email.provider}`)} · ${s.email.enabled ? t("security.enabled") : t("security.disabled")}`,
              ],
            ]}
          />
          {!s.email.enabled ? (
            <Alert variant="warning" className="mt-4">
              {t("admin.email_disabled_help")}
            </Alert>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("admin.storage")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm">
            {Object.entries(s.storage.buckets ?? {}).map(([b, bytes]) => (
              <li key={b} className="flex justify-between gap-4">
                <code>{b}</code>
                <span>{formatBytes(bytes, i18n.language)}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
