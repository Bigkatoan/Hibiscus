import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiUrl } from "@/api/client";
import { useHfTokenStatus } from "@/api/hooks/auth";
import {
  useDeleteModel,
  useModel,
  useModelFiles,
  usePushModelToHub,
  useRenameModel,
  useReverifyModel,
} from "@/api/hooks/models";
import { ConfirmButton, CopyButton, ErrorAlert, KeyValue, PageHeader, PageLoader } from "@/components/common";
import { Field } from "@/components/Field";
import { ModelStatusBadge, VerifiedBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input } from "@/components/ui/input";
import { Alert, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { useCan, useWorkspace, useWsPath } from "@/features/workspace/context";
import { formatBytes, formatDateTime, formatInt, formatNumber } from "@/lib/format";
import { modelDownloadUrl, OnnxBadge } from "./ModelsPage";

function Check({ ok, label }: { ok: boolean | null | undefined; label: string }) {
  const { t } = useTranslation();
  const glyph = ok === true ? "check" : ok === false ? "close" : "help";
  return (
    <li className="flex items-center gap-2 text-sm">
      <PxIcon
        name={glyph}
        className={ok === true ? "text-success" : ok === false ? "text-destructive" : "text-muted-foreground"}
      />
      <span>{label}</span>
      <span className="sr-only">
        {ok === true ? t("model.check_ok") : ok === false ? t("model.check_failed") : t("model.check_na")}
      </span>
    </li>
  );
}

function HubPushCard({ modelId }: { modelId: string }) {
  const { t } = useTranslation();
  const hf = useHfTokenStatus();
  const push = usePushModelToHub(modelId);
  const form = useForm<{ repo_id: string; private: boolean; include_onnx: boolean }>({
    defaultValues: { repo_id: "", private: true, include_onnx: true },
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PxIcon name="upload" />
          {t("model.push_hub")}
        </CardTitle>
        <CardDescription>{t("model.push_hub_help")}</CardDescription>
      </CardHeader>
      <CardContent>
        {hf.data && !hf.data.present ? (
          <Alert variant="warning">
            {t("errors.hf_token_missing")}{" "}
            <Link to="/account/integrations" className="text-primary underline">
              {t("model.set_hf_token")}
            </Link>
          </Alert>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(e) =>
              void form
                .handleSubmit((v) => push.mutateAsync(v))(e)
                .catch(() => undefined)
            }
          >
            <Field label={t("model.repo_id")} required description="org/name">
              <Input
                spellCheck={false}
                {...form.register("repo_id", { required: true, pattern: /^[\w.-]+\/[\w.-]+$/ })}
              />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox {...form.register("private")} />
              {t("model.private_repo")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox {...form.register("include_onnx")} />
              {t("model.include_onnx")}
            </label>
            <ErrorAlert error={push.error} />
            {push.isSuccess ? <Alert variant="success">{t("model.push_queued")}</Alert> : null}
            <Button type="submit" disabled={push.isPending}>
              {t("model.push")}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

/** One copyable shell command (mobile friendly: wraps, Copy button underneath). */
function CommandBlock({ cmd, testId }: { cmd: string; testId?: string }) {
  return (
    <div className="space-y-1">
      <code className="block whitespace-pre-wrap break-all rounded bg-muted p-2 text-xs" data-testid={testId}>
        {cmd}
      </code>
      <CopyButton value={cmd} />
    </div>
  );
}

/**
 * "Run it on the robot" (CX-02, UAT-49/60, wireframes S-15): LeLab cannot run policies, so the
 * user runs the bundle's run_on_robot.sh (LeRobot CLI) inside the LeLab venv.
 */
function RunOnRobotCard({ bundleName, pullCmd }: { bundleName: string; pullCmd: string }) {
  const { t } = useTranslation();
  const steps: { label: string; cmd: string }[] = [
    { label: t("model.run_on_robot.step_pull"), cmd: pullCmd },
    { label: t("model.run_on_robot.step_cd"), cmd: `cd ~/lelab/models/${bundleName}` },
    { label: t("model.run_on_robot.step_venv"), cmd: "source ~/lelab/leLab/.venv/bin/activate" },
    { label: t("model.run_on_robot.step_port"), cmd: "lerobot-find-port" },
    {
      label: t("model.run_on_robot.step_run"),
      cmd: "PORT=/dev/ttyACM0 ROBOT_ID=my_follower DURATION=20 ./run_on_robot.sh",
    },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("model.run_on_robot.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert variant="warning" data-testid="no-inference">
          {t("model.run_on_robot.no_inference")}
        </Alert>
        <ol className="space-y-3">
          {steps.map((s, i) => (
            <li key={s.cmd} className="space-y-1">
              <p className="text-sm font-medium">
                {i + 1}. {s.label}
              </p>
              <CommandBlock cmd={s.cmd} />
            </li>
          ))}
        </ol>
        <Alert variant="warning">{t("model.run_on_robot.safety")}</Alert>
        <p className="text-xs text-muted-foreground">{t("model.run_on_robot.guide")}</p>
      </CardContent>
    </Card>
  );
}

/** getModel + listModelFiles + download / verify / push-hub / rename / delete. */
export function ModelDetailPage() {
  const { t, i18n } = useTranslation();
  const { modelId = "" } = useParams();
  const ws = useWorkspace();
  const path = useWsPath();
  const navigate = useNavigate();
  const canWrite = useCan("member");
  const canAdmin = useCan("admin");
  const model = useModel(modelId);
  const files = useModelFiles(modelId, model.data?.status === "ready");
  const reverify = useReverifyModel(modelId);
  const rename = useRenameModel(modelId);
  const del = useDeleteModel(ws.workspace_id);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  if (model.isPending) return <PageLoader />;
  if (model.isError) return <ErrorAlert error={model.error} />;
  const m = model.data;
  const v = m.verification;
  // pull writes <to>/<bundle_name>, so --to is the parent folder (CX-09).
  const pullCmd = `hibiscus pull ${m.id} --to ~/lelab/models`;
  const bundleName = files.data?.bundle_name ?? m.name;
  return (
    <div className="mx-auto min-w-0 max-w-6xl space-y-6">
      <PageHeader
        title={
          editing ? (
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                rename.mutate(name, {
                  onSuccess: () => {
                    setEditing(false);
                  },
                });
              }}
            >
              <label htmlFor="model-name" className="sr-only">
                {t("models.name")}
              </label>
              <Input
                id="model-name"
                value={name}
                maxLength={100}
                onChange={(e) => {
                  setName(e.target.value);
                }}
              />
              <Button type="submit" size="sm">
                {t("common.save")}
              </Button>
            </form>
          ) : (
            <span className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 max-w-full [overflow-wrap:anywhere]">{m.name}</span>
              {canWrite ? (
                <Button
                  variant="link"
                  size="sm"
                  onClick={() => {
                    setName(m.name);
                    setEditing(true);
                  }}
                >
                  {t("common.rename")}
                </Button>
              ) : null}
            </span>
          )
        }
        description={t("model.subtitle", {
          policy: m.policy_type.toUpperCase(),
          run: m.run_number,
          step: formatInt(m.step, i18n.language),
        })}
        actions={
          <>
            {m.status === "ready" ? (
              <Button asChild>
                <a href={modelDownloadUrl(m.id)}>
                  <PxIcon name="download" />
                  {t("model.download")}
                </a>
              </Button>
            ) : null}
            {canWrite && m.status === "ready" ? (
              <Button
                variant="outline"
                disabled={reverify.isPending}
                onClick={() => {
                  reverify.mutate();
                }}
              >
                <PxIcon name="refresh" />
                {t("model.reverify")}
              </Button>
            ) : null}
            {canAdmin ? (
              <ConfirmButton
                variant="ghost"
                destructive
                aria-label={t("common.delete")}
                title={t("model.delete_confirm", { name: m.name })}
                confirmLabel={t("common.delete")}
                onConfirm={async () => {
                  await del.mutateAsync(m.id);
                  navigate(path("models"));
                }}
              >
                <PxIcon name="trash" />
              </ConfirmButton>
            ) : null}
          </>
        }
      />
      <ErrorAlert error={reverify.error ?? rename.error} />
      {m.error_message ? <Alert variant="destructive">{m.error_message}</Alert> : null}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              {t("model.verification")}
              <ModelStatusBadge status={m.status} />
              {m.status === "ready" ? <VerifiedBadge verified={m.verified} /> : null}
              <OnnxBadge status={m.onnx_status} />
            </CardTitle>
            <CardDescription>
              {t("model.verification_help")} {t("model.verified_not_success")}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <ul className="space-y-1">
              <Check ok={v?.load_ok} label={t("model.check_load")} />
              <Check ok={v?.parity_ok} label={t("model.check_parity")} />
              <Check ok={v?.manifest_ok} label={t("model.check_manifest")} />
            </ul>
            {v?.parity ? (
              <p className="text-xs text-muted-foreground">
                {t("model.parity_detail", {
                  diff: formatNumber(v.parity.max_abs_diff ?? null, i18n.language),
                  atol: formatNumber(v.parity.atol ?? null, i18n.language),
                  n: v.parity.n_samples ?? 0,
                })}
              </p>
            ) : null}
            {m.onnx_detail ? <p className="text-xs text-muted-foreground">{m.onnx_detail}</p> : null}
            {v?.checked_at ? (
              <p className="text-xs text-muted-foreground">
                {t("model.checked_at", { date: formatDateTime(v.checked_at, i18n.language) })}
              </p>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("model.details")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <KeyValue
              items={[
                [
                  t("models.run"),
                  <Link key="r" className="text-primary hover:underline" to={path(`runs/${m.run_id}`)}>
                    #{m.run_number}
                  </Link>,
                ],
                [t("runs.dataset"), m.dataset ? `${m.dataset.name ?? ""} v${m.dataset.version ?? ""}` : "—"],
                [t("datasets.size"), formatBytes(m.bundle_size_bytes, i18n.language)],
                [t("models.mae"), formatNumber(m.eval_summary?.action_mae ?? null, i18n.language)],
                [
                  "SHA-256",
                  <code key="s" className="break-all text-xs">
                    {m.bundle_sha256 ?? "—"}
                  </code>,
                ],
                [t("model.hub"), m.hub_repo_id ?? "—"],
              ]}
            />
            {m.eval_summary ? (
              <Alert variant="warning" data-testid="mae-disclaimer">
                {t("eval.offline_not_success_rate")}
              </Alert>
            ) : null}
            <div>
              <p className="mb-1 text-sm font-medium">{t("model.pull_cli")}</p>
              <CommandBlock cmd={pullCmd} testId="pull-cmd" />
            </div>
          </CardContent>
        </Card>
      </div>
      {m.status === "ready" ? <RunOnRobotCard bundleName={bundleName} pullCmd={pullCmd} /> : null}
      {files.data ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("model.files", { name: files.data.bundle_name })}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <THead>
                <TR>
                  <TH>{t("model.path")}</TH>
                  <TH>{t("datasets.size")}</TH>
                  <TH>SHA-256</TH>
                </TR>
              </THead>
              <TBody>
                {files.data.files.map((f) => (
                  <TR key={f.path}>
                    <TD>
                      <a
                        className="font-mono text-xs text-primary hover:underline"
                        href={apiUrl(
                          `/models/${m.id}/files/${f.path.split("/").map(encodeURIComponent).join("/")}`,
                        )}
                      >
                        {f.path}
                      </a>
                    </TD>
                    <TD>{formatBytes(f.size, i18n.language)}</TD>
                    <TD>
                      <code className="text-xs">{f.sha256.slice(0, 16)}…</code>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
      {canWrite && m.status === "ready" ? <HubPushCard modelId={m.id} /> : null}
    </div>
  );
}
