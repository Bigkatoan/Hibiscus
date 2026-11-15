import { zodResolver } from "@hookform/resolvers/zod";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import type { Schemas } from "@/api/client";
import { useApiTokens, useCreateApiToken, useMe, useRevokeApiToken } from "@/api/hooks/auth";
import { ConfirmButton, CopyButton, EmptyState, ErrorAlert, PageLoader } from "@/components/common";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Checkbox, Input, NativeSelect } from "@/components/ui/input";
import { Alert, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export const PAT_SCOPES: Schemas["PatScope"][] = [
  "datasets:read",
  "datasets:write",
  "runs:read",
  "runs:write",
  "models:read",
];

/**
 * Scope presets (docs/user-guide 03 §3.2, UAT-20). "Máy collect" covers every CLI command:
 * push (datasets:write), train (runs:write), logs/runs (runs:read), pull (models:read).
 */
export const TOKEN_PRESETS = {
  collect: ["datasets:read", "datasets:write", "runs:read", "runs:write", "models:read"],
  readonly: ["datasets:read", "runs:read", "models:read"],
} as const satisfies Record<string, readonly Schemas["PatScope"][]>;
export type TokenPresetId = keyof typeof TOKEN_PRESETS | "custom";

export function presetForScopes(scopes: readonly string[]): TokenPresetId {
  for (const [id, list] of Object.entries(TOKEN_PRESETS) as [keyof typeof TOKEN_PRESETS, readonly string[]][])
    if (list.length === scopes.length && list.every((s) => scopes.includes(s))) return id;
  return "custom";
}

const createSchema = z.object({
  name: z.string().trim().min(1, "validation.required").max(100),
  workspace_id: z.string().uuid("validation.required"),
  scopes: z
    .array(z.enum(["datasets:read", "datasets:write", "runs:read", "runs:write", "models:read"]))
    .min(1, "validation.scopes"),
  expires_in_days: z.string(),
});
type CreateValues = z.infer<typeof createSchema>;

function CreateTokenDialog({ defaultWorkspaceId }: { defaultWorkspaceId?: string }) {
  const { t } = useTranslation();
  const me = useMe();
  const create = useCreateApiToken();
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<Schemas["ApiTokenCreated"] | null>(null);
  // The plaintext token is shown exactly once: the dialog cannot be closed (Esc, outside click,
  // X) until the user confirms they copied it (CX-03, UAT-20).
  const [copiedAck, setCopiedAck] = useState(false);
  const locked = !!created && !copiedAck;
  const loginCmd = `hibiscus login --server ${window.location.origin}`;
  // Scope/role compatibility (e.g. viewer + write scope) is enforced server-side (403).
  const memberships = me.data?.memberships ?? [];
  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      name: "",
      workspace_id: defaultWorkspaceId ?? memberships[0]?.workspace_id ?? "",
      scopes: [...TOKEN_PRESETS.collect],
      expires_in_days: "90",
    },
  });
  const scopes = form.watch("scopes");
  const presetId = presetForScopes(scopes);
  const onSubmit = form.handleSubmit(async (v) => {
    // Contract: `expires_in_days: integer | null` (null = never). openapi-typescript 7.5 drops the
    // `null` member when a default is present, so the literal is asserted to the generated type.
    const body = {
      name: v.name,
      workspace_id: v.workspace_id,
      scopes: v.scopes,
      expires_in_days: v.expires_in_days === "never" ? null : Number(v.expires_in_days),
    } as Schemas["ApiTokenCreate"];
    const res = await create.mutateAsync(body);
    setCreated(res);
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o && locked) return;
        setOpen(o);
        if (!o) {
          setCreated(null);
          setCopiedAck(false);
          form.reset();
          create.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <PxIcon name="plus" />
          {t("tokens.create")}
        </Button>
      </DialogTrigger>
      <DialogContent hideClose={locked}>
        <DialogHeader>
          <DialogTitle>{t("tokens.create")}</DialogTitle>
          <DialogDescription>{t("tokens.create_help")}</DialogDescription>
        </DialogHeader>
        {created ? null : (
          <p className="text-xs text-muted-foreground" data-testid="token-admin-2fa-note">
            {t("tokens.admin_requires_2fa")}
          </p>
        )}
        {created ? (
          <div className="space-y-3">
            <Alert variant="warning">{t("tokens.shown_once")}</Alert>
            <code className="block break-all rounded bg-muted p-3 text-sm" data-testid="new-token">
              {created.token}
            </code>
            <CopyButton value={created.token} />
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">{t("tokens.cli_hint")}</p>
              <div className="flex flex-wrap items-center gap-2">
                <code className="break-all rounded bg-muted px-2 py-1 text-xs" data-testid="login-cmd">
                  {loginCmd}
                </code>
                <CopyButton value={loginCmd} />
              </div>
              <p className="text-xs text-muted-foreground">{t("tokens.cli_paste")}</p>
            </div>
            <label className="flex items-center gap-2 text-sm font-medium">
              <Checkbox
                checked={copiedAck}
                onChange={(e) => {
                  setCopiedAck(e.target.checked);
                }}
              />
              {t("tokens.copied_ack")}
            </label>
            <DialogFooter>
              <Button
                disabled={!copiedAck}
                onClick={() => {
                  setOpen(false);
                  setCreated(null);
                  setCopiedAck(false);
                  form.reset();
                  create.reset();
                }}
              >
                {t("tokens.done")}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={(e) => void onSubmit(e).catch(() => undefined)} className="space-y-4" noValidate>
            <Field
              label={t("tokens.name")}
              required
              error={form.formState.errors.name?.message ? t(form.formState.errors.name.message) : undefined}
            >
              <Input placeholder="collect-pc" {...form.register("name")} />
            </Field>
            <Field label={t("tokens.workspace")} required>
              <NativeSelect {...form.register("workspace_id")}>
                {memberships.map((m) => (
                  <option key={m.workspace_id} value={m.workspace_id}>
                    {m.workspace_name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">{t("tokens.preset")}</legend>
              <div className="flex flex-wrap gap-2">
                {(["collect", "readonly", "custom"] as const).map((id) => (
                  <label
                    key={id}
                    className={cn(
                      "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm",
                      presetId === id && "border-primary bg-primary/5",
                    )}
                  >
                    <input
                      type="radio"
                      name="token-preset"
                      value={id}
                      checked={presetId === id}
                      onChange={() => {
                        if (id !== "custom")
                          form.setValue("scopes", [...TOKEN_PRESETS[id]], { shouldValidate: true });
                      }}
                    />
                    {t(`tokens.presets.${id}`)}
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">{t(`tokens.presets.${presetId}_help`)}</p>
            </fieldset>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">{t("tokens.scopes")}</legend>
              {PAT_SCOPES.map((s) => (
                <label key={s} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={scopes.includes(s)}
                    onChange={(e) => {
                      const next = e.target.checked ? [...scopes, s] : scopes.filter((x) => x !== s);
                      form.setValue("scopes", next, { shouldValidate: true });
                    }}
                  />
                  <code>{s}</code>
                  <span className="text-muted-foreground">{t(`tokens.scope.${s.replace(":", "_")}`)}</span>
                </label>
              ))}
              {form.formState.errors.scopes?.message ? (
                <p className="text-xs text-destructive">{t(form.formState.errors.scopes.message)}</p>
              ) : null}
            </fieldset>
            <Field label={t("tokens.expires")}>
              <NativeSelect {...form.register("expires_in_days")}>
                <option value="30">{t("tokens.days", { count: 30 })}</option>
                <option value="90">{t("tokens.days", { count: 90 })}</option>
                <option value="365">{t("tokens.days", { count: 365 })}</option>
                <option value="never">{t("tokens.never")}</option>
              </NativeSelect>
            </Field>
            <ErrorAlert error={create.error} />
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <PxIcon name="spinner" className="px-spin" /> : <PxIcon name="key" />}
              {t("tokens.create")}
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** listApiTokens / createApiToken / revokeApiToken. Optionally filtered to one workspace. */
export function TokensPanel({ workspaceId }: { workspaceId?: string }) {
  const { t, i18n } = useTranslation();
  const tokens = useApiTokens();
  const me = useMe();
  const revoke = useRevokeApiToken();
  if (tokens.isPending) return <PageLoader />;
  if (tokens.isError) return <ErrorAlert error={tokens.error} />;
  const wsName = (id: string) =>
    me.data?.memberships.find((m) => m.workspace_id === id)?.workspace_name ?? id.slice(0, 8);
  const items = tokens.data.items.filter((tk) => !workspaceId || tk.workspace_id === workspaceId);
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <CreateTokenDialog {...(workspaceId ? { defaultWorkspaceId: workspaceId } : {})} />
      </div>
      {items.length === 0 ? (
        <EmptyState title={t("tokens.empty")} description={t("tokens.create_help")} />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>{t("tokens.name")}</TH>
              <TH>{t("tokens.workspace")}</TH>
              <TH>{t("tokens.scopes")}</TH>
              <TH>{t("tokens.last_used")}</TH>
              <TH>{t("tokens.expires")}</TH>
              <TH>
                <span className="sr-only">{t("common.actions")}</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {items.map((tk) => (
              <TR key={tk.id}>
                <TD>
                  <div className="font-medium">{tk.name}</div>
                  <code className="text-xs text-muted-foreground">hbp_{tk.prefix}_…</code>
                </TD>
                <TD>{wsName(tk.workspace_id)}</TD>
                <TD>
                  <div className="flex flex-wrap gap-1">
                    {tk.scopes.map((s) => (
                      <Badge key={s} variant="secondary">
                        {s}
                      </Badge>
                    ))}
                  </div>
                </TD>
                <TD>
                  {tk.last_used_at ? formatDateTime(tk.last_used_at, i18n.language) : t("tokens.never_used")}
                  {tk.last_used_at && tk.last_used_ip ? (
                    <div className="text-xs text-muted-foreground">
                      {t("tokens.last_used_from", { ip: tk.last_used_ip })}
                    </div>
                  ) : null}
                </TD>
                <TD>{tk.expires_at ? formatDateTime(tk.expires_at, i18n.language) : t("tokens.never")}</TD>
                <TD className="text-right">
                  {tk.revoked_at ? (
                    <Badge variant="outline">{t("tokens.revoked")}</Badge>
                  ) : (
                    <ConfirmButton
                      variant="outline"
                      size="sm"
                      destructive
                      title={t("tokens.revoke_confirm", { name: tk.name })}
                      confirmLabel={t("tokens.revoke")}
                      onConfirm={() => revoke.mutateAsync(tk.id)}
                    >
                      {t("tokens.revoke")}
                    </ConfirmButton>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
