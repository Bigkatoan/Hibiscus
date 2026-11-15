import { PxIcon } from "@/hibiscus/PixelAnim";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { Schemas } from "@/api/client";
import {
  isRunTerminal,
  useCancelRun,
  useCheckpointEval,
  useCheckpoints,
  useEvalCheckpoint,
  useExportCheckpoint,
  usePauseRun,
  useResumeRun,
  useRun,
  useRunManifest,
  useUpdateRun,
} from "@/api/hooks/runs";
import { useModel } from "@/api/hooks/models";
import { useGpus } from "@/api/hooks/workspaces";
import { LineChart } from "@/components/charts/LineChart";
import { ConfirmButton, ErrorAlert, KeyValue, PageHeader, PageLoader } from "@/components/common";
import { Field } from "@/components/Field";
import { hibiForRunStatus } from "@/lib/hibi";
import { Mascot } from "@/components/Mascot";
import { RunStatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input, NativeSelect } from "@/components/ui/input";
import { Alert, Progress, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan, useWsPath } from "@/features/workspace/context";
import { formatBytes, formatDateTime, formatDuration, formatInt, formatNumber } from "@/lib/format";
import { LogViewer } from "./LogViewer";
import { buildMetricCharts } from "./metricGroups";
import { cloneHref, recoveryActions } from "./recovery";
import { useRunStream, type RunStreamState } from "./runStream";
import { progressPct } from "./RunsPage";

type S = Schemas;

function PauseDialog({ run }: { run: S["Run"] }) {
  const { t, i18n } = useTranslation();
  const pause = usePauseRun();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"next_checkpoint" | "now">("next_checkpoint");
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <PxIcon name="pause" />
          {t("run.pause")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("run.pause")}</DialogTitle>
          <DialogDescription>{t("run.pause_help")}</DialogDescription>
        </DialogHeader>
        <fieldset className="space-y-2 text-sm">
          <legend className="sr-only">{t("run.pause_mode")}</legend>
          <label className="flex items-start gap-2 rounded border p-3">
            <input
              type="radio"
              name="pause-mode"
              checked={mode === "next_checkpoint"}
              onChange={() => {
                setMode("next_checkpoint");
              }}
            />
            <span>
              <span className="font-medium">{t("run.pause_next_checkpoint")}</span>
              <span className="block text-muted-foreground">
                {run.progress.next_checkpoint_step
                  ? t("run.pause_next_checkpoint_at", {
                      step: formatInt(run.progress.next_checkpoint_step, i18n.language),
                    })
                  : t("run.pause_next_checkpoint_help")}
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2 rounded border p-3">
            <input
              type="radio"
              name="pause-mode"
              checked={mode === "now"}
              onChange={() => {
                setMode("now");
              }}
            />
            <span>
              <span className="font-medium">{t("run.pause_now")}</span>
              <span className="block text-muted-foreground">
                {t("run.pause_now_help", {
                  step: formatInt(run.progress.last_checkpoint_step ?? 0, i18n.language),
                })}
              </span>
            </span>
          </label>
        </fieldset>
        <ErrorAlert error={pause.error} />
        <DialogFooter>
          <Button
            disabled={pause.isPending}
            onClick={() => {
              pause.mutate(
                { id: run.id, mode },
                {
                  onSuccess: () => {
                    setOpen(false);
                  },
                },
              );
            }}
          >
            {t("run.pause")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResumeDialog({ run, label }: { run: S["Run"]; label?: string }) {
  const { t, i18n } = useTranslation();
  const resume = useResumeRun();
  const gpus = useGpus(false);
  const [open, setOpen] = useState(false);
  const form = useForm<{ gpu: string; total_steps: string }>({
    defaultValues: { gpu: run.requested_gpu ?? "auto", total_steps: "" },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <PxIcon name="play" />
          {label ?? t("run.resume")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("run.resume")}</DialogTitle>
          <DialogDescription>
            {t("run.resume_help", {
              step: formatInt(run.progress.last_checkpoint_step ?? 0, i18n.language),
            })}
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) =>
            void form.handleSubmit((v) => {
              const total = v.total_steps.trim() ? Number(v.total_steps) : undefined;
              resume.mutate(
                { id: run.id, body: { gpu: v.gpu, ...(total ? { total_steps: total } : {}) } },
                {
                  onSuccess: () => {
                    setOpen(false);
                  },
                },
              );
            })(e)
          }
        >
          <Field label={t("wizard.gpu")}>
            <NativeSelect {...form.register("gpu")}>
              <option value="auto">{t("gpu.auto")}</option>
              {(gpus.data?.items ?? []).map((g) => (
                <option key={g.id} value={g.id}>
                  {g.id} · {g.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field
            label={t("run.total_steps")}
            description={t("run.total_steps_help", {
              steps: formatInt(run.progress.total_steps, i18n.language),
            })}
          >
            <Input type="number" min={run.progress.current_step + 1} {...form.register("total_steps")} />
          </Field>
          <ErrorAlert error={resume.error} />
          <Button type="submit" disabled={resume.isPending}>
            {t("run.resume")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EditDialog({ run }: { run: S["Run"] }) {
  const { t } = useTranslation();
  const update = useUpdateRun();
  const [open, setOpen] = useState(false);
  const form = useForm<{ name: string; priority: number }>({
    defaultValues: { name: run.name, priority: run.priority },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("run.edit")}>
          <PxIcon name="edit" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("run.edit")}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) =>
            void form.handleSubmit((v) => {
              update.mutate(
                { id: run.id, body: { name: v.name, priority: Number(v.priority) } },
                {
                  onSuccess: () => {
                    setOpen(false);
                  },
                },
              );
            })(e)
          }
        >
          <Field label={t("wizard.run_name")}>
            <Input maxLength={100} {...form.register("name", { required: true })} />
          </Field>
          <Field label={t("run.priority")} description={t("run.priority_help")}>
            <Input type="number" {...form.register("priority")} />
          </Field>
          <ErrorAlert error={update.error} />
          <Button type="submit" disabled={update.isPending}>
            {t("common.save")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function MetricsTab({ stream }: { stream: RunStreamState }) {
  const { t } = useTranslation();
  const [smoothing, setSmoothing] = useState(0);
  const charts = useMemo(
    () => buildMetricCharts(stream.metrics, smoothing),
    // metricsVersion changes whenever buffers change
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stream.metricsVersion, smoothing],
  );
  // Permanent, non-dismissable (copy-deck §5, UAT-39): low offline loss is not robot success.
  const honesty = (
    <Alert variant="warning" data-testid="metrics-honesty">
      <p className="flex items-center gap-2 font-medium">
        <PxIcon name="info" className="shrink-0" />
        {t("run.metrics_honesty.title")}
      </p>
      <p className="mt-1">{t("run.metrics_honesty.body")}</p>
    </Alert>
  );
  if (!charts.length)
    return (
      <div className="space-y-4">
        {honesty}
        <p className="py-10 text-center text-sm text-muted-foreground">{t("run.no_metrics")}</p>
      </div>
    );
  return (
    <div className="space-y-4">
      {honesty}
      <label className="flex max-w-xs items-center gap-3 text-sm">
        <span className="shrink-0">{t("run.smoothing")}</span>
        <input
          type="range"
          min={0}
          max={0.99}
          step={0.01}
          value={smoothing}
          onChange={(e) => {
            setSmoothing(Number(e.target.value));
          }}
          className="w-full"
          aria-valuetext={String(smoothing)}
        />
        <span className="w-10 text-right tabular-nums">{smoothing.toFixed(2)}</span>
      </label>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {charts.map((c) => (
          <LineChart
            key={c.id}
            title={c.id.startsWith("other:") ? c.id.slice(6) : t(`run.chart.${c.id}`)}
            series={c.series}
            xLabel={t("run.step")}
            logY={c.logY}
            syncKey="run-metrics"
          />
        ))}
      </div>
    </div>
  );
}

function TelemetryTab({ stream }: { stream: RunStreamState }) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language;
  const samples = stream.telemetry;
  const xs = samples.map((s) => new Date(s.ts).getTime() / 1000);
  const t0 = xs[0] ?? 0;
  const rel = xs.map((x) => Math.round(x - t0));
  const last = samples.at(-1);
  return (
    <div className="space-y-4">
      {last ? (
        <KeyValue
          items={[
            ["GPU", last.gpu_id],
            [t("gpu.util"), `${formatNumber(last.util_pct, lng)} %`],
            [
              t("gpu.memory"),
              `${formatNumber(last.mem_used_mb / 1024, lng, 3)} / ${formatNumber(last.mem_total_mb / 1024, lng, 3)} GB`,
            ],
            [t("gpu.temperature"), `${formatNumber(last.temperature_c, lng)} °C`],
            [t("gpu.power"), `${formatNumber(last.power_w, lng)} W`],
          ]}
        />
      ) : (
        <p className="py-6 text-center text-sm text-muted-foreground">{t("gpu.no_telemetry")}</p>
      )}
      {samples.length > 1 ? (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <LineChart
            title={t("gpu.util")}
            xLabel={t("gpu.seconds")}
            series={[{ label: "util %", x: rel, y: samples.map((s) => s.util_pct) }]}
          />
          <LineChart
            title={t("gpu.memory")}
            xLabel={t("gpu.seconds")}
            series={[{ label: "MiB", x: rel, y: samples.map((s) => s.mem_used_mb) }]}
          />
          <LineChart
            title={t("gpu.temperature")}
            xLabel={t("gpu.seconds")}
            series={[{ label: "°C", x: rel, y: samples.map((s) => s.temperature_c) }]}
          />
          <LineChart
            title={t("gpu.power")}
            xLabel={t("gpu.seconds")}
            series={[{ label: "W", x: rel, y: samples.map((s) => s.power_w) }]}
          />
        </div>
      ) : null}
    </div>
  );
}

function EvalResult({ runId, step }: { runId: string; step: number }) {
  const { t, i18n } = useTranslation();
  const res = useCheckpointEval(runId, step);
  if (res.isPending) return <PageLoader />;
  if (res.isError) return <ErrorAlert error={res.error} />;
  const e = res.data;
  return (
    <div className="space-y-3">
      <Alert variant="warning">{t(e.disclaimer_key)}</Alert>
      <KeyValue
        items={[
          ["MAE", formatNumber(e.overall.mae, i18n.language)],
          ["MSE", formatNumber(e.overall.mse, i18n.language)],
          [t("eval.frames"), formatInt(e.n_frames, i18n.language)],
          [t("eval.heldout"), e.heldout_episodes.join(", ")],
        ]}
      />
      <Table>
        <THead>
          <TR>
            <TH>{t("eval.joint")}</TH>
            <TH>MAE</TH>
            <TH>MSE</TH>
          </TR>
        </THead>
        <TBody>
          {e.per_joint.map((j) => (
            <TR key={j.name}>
              <TD>{j.name}</TD>
              <TD>{formatNumber(j.mae, i18n.language)}</TD>
              <TD>{formatNumber(j.mse, i18n.language)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function CheckpointsTab({ run }: { run: S["Run"] }) {
  const { t, i18n } = useTranslation();
  const path = useWsPath();
  const canWrite = useCan("member");
  const cps = useCheckpoints(run.id);
  const exportCp = useExportCheckpoint(run.id);
  const evalCp = useEvalCheckpoint(run.id);
  const [evalStep, setEvalStep] = useState<number | null>(null);
  if (cps.isPending) return <PageLoader />;
  if (cps.isError) return <ErrorAlert error={cps.error} />;
  return (
    <div className="space-y-4">
      <ErrorAlert error={exportCp.error ?? evalCp.error} />
      {cps.data.items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">{t("run.no_checkpoints")}</p>
      ) : null}
      {cps.data.items.length > 0 ? (
        <Table>
          <THead>
            <TR>
              <TH>{t("run.step")}</TH>
              <TH>{t("datasets.size")}</TH>
              <TH>{t("run.eval")}</TH>
              <TH>{t("common.created")}</TH>
              <TH>
                <span className="sr-only">{t("common.actions")}</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {cps.data.items.map((c) => (
              <TR key={c.id}>
                <TD>
                  {formatInt(c.step, i18n.language)}{" "}
                  {c.is_last ? <Badge variant="secondary">{t("run.last")}</Badge> : null}
                </TD>
                <TD>{formatBytes(c.size_bytes, i18n.language)}</TD>
                <TD>
                  {c.eval_summary ? (
                    <Button
                      variant="link"
                      className="h-auto p-0"
                      onClick={() => {
                        setEvalStep(c.step);
                      }}
                    >
                      {t("run.view_eval")}
                    </Button>
                  ) : (
                    "—"
                  )}
                </TD>
                <TD>{formatDateTime(c.created_at, i18n.language)}</TD>
                <TD className="space-x-1 text-right">
                  {c.model_id ? (
                    <Button variant="outline" size="sm" asChild>
                      <Link to={path(`models/${c.model_id}`)}>{t("run.open_model")}</Link>
                    </Button>
                  ) : canWrite ? (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={exportCp.isPending}
                      onClick={() => {
                        exportCp.mutate({ step: c.step, options: { onnx: true, eval: true } });
                      }}
                    >
                      {t("run.export")}
                    </Button>
                  ) : null}
                  {canWrite ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={evalCp.isPending}
                      onClick={() => {
                        evalCp.mutate(c.step);
                      }}
                    >
                      {t("run.run_eval")}
                    </Button>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}
      {evalCp.isSuccess ? <Alert variant="success">{t("run.eval_queued")}</Alert> : null}
      {evalStep !== null ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("run.eval_title", { step: formatInt(evalStep, i18n.language) })}</CardTitle>
          </CardHeader>
          <CardContent>
            <EvalResult runId={run.id} step={evalStep} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function ConfigTab({ run }: { run: S["Run"] }) {
  const { t } = useTranslation();
  const manifest = useRunManifest(run.id, run.status !== "queued");
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div>
        <h3 className="mb-2 font-extrabold text-base">{t("run.config")}</h3>
        <pre className="max-h-[32rem] overflow-auto rounded bg-muted p-3 text-xs">
          {JSON.stringify(run.config, null, 2)}
        </pre>
      </div>
      <div>
        <h3 className="mb-2 font-extrabold text-base">{t("run.manifest")}</h3>
        {manifest.data ? (
          <div className="space-y-3">
            <KeyValue
              items={[
                ["LeRobot", manifest.data.lerobot_version],
                ["torch", manifest.data.torch_version],
                ["CUDA", manifest.data.cuda_version],
                ["Python", manifest.data.python_version],
                [t("run.gpu"), `${manifest.data.gpu.name} (${manifest.data.gpu.id})`],
                [t("wizard.seed"), `${manifest.data.seed}`],
                [
                  t("datasets.content_hash"),
                  <code key="h" className="break-all text-xs">
                    {manifest.data.dataset.content_hash}
                  </code>,
                ],
                [
                  t("run.image"),
                  <code key="i" className="break-all text-xs">
                    {manifest.data.image_digest}
                  </code>,
                ],
              ]}
            />
            <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs">
              {manifest.data.lerobot_args.join(" ")}
            </pre>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t("run.manifest_pending")}</p>
        )}
      </div>
    </div>
  );
}

/** getRun + SSE live view: metrics charts, logs, GPU telemetry, checkpoints, config. */
export function RunDetailPage() {
  const { t, i18n } = useTranslation();
  const { runId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const path = useWsPath();
  const canWrite = useCan("member");
  const runQ = useRun(runId);
  const cancel = useCancelRun();
  const run = runQ.data;
  const live = !!run && !isRunTerminal(run.status);
  const stream = useRunStream(runId, live);
  const tab = params.get("tab") ?? "metrics";
  const model = useModel(run?.model_id ?? "");
  const gpus = useGpus(false);

  if (runQ.isPending) return <PageLoader />;
  if (runQ.isError || !run) return <ErrorAlert error={runQ.error} />;
  const actions = new Set(run.allowed_actions ?? []);
  const p = run.progress;
  const mood = hibiForRunStatus(run.status);
  const lng = i18n.language;
  const terminal = isRunTerminal(run.status);
  const mae = model.data?.eval_summary?.action_mae ?? null;
  const recovery = canWrite ? recoveryActions(run, gpus.data?.items ?? []) : [];
  return (
    <div className="mx-auto min-w-0 max-w-7xl space-y-6">
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            <span className="min-w-0 max-w-full [overflow-wrap:anywhere]">
              #{run.number} {run.name}
            </span>{" "}
            <RunStatusBadge status={run.status} />
            {canWrite && actions.has("edit") ? <EditDialog run={run} /> : null}
          </span>
        }
        description={t("run.subtitle", {
          policy: run.policy_type.toUpperCase(),
          dataset: run.dataset.name,
          version: run.dataset.version,
          user: run.created_by.display_name,
        })}
        actions={
          canWrite ? (
            <>
              {actions.has("pause") ? <PauseDialog run={run} /> : null}
              {actions.has("resume") ? <ResumeDialog run={run} /> : null}
              {actions.has("clone") ? (
                <Button variant="outline" onClick={() => navigate(path(`runs/new?clone=${run.id}`))}>
                  <PxIcon name="copy" />
                  {t("run.clone")}
                </Button>
              ) : null}
              {actions.has("cancel") ? (
                <ConfirmButton
                  variant="destructive"
                  destructive
                  title={t("run.cancel_confirm", { name: run.name })}
                  confirmLabel={t("run.cancel")}
                  onConfirm={() => cancel.mutateAsync(run.id)}
                >
                  <PxIcon name="ban" />
                  {t("run.cancel")}
                </ConfirmButton>
              ) : null}
            </>
          ) : null
        }
      />
      {run.error_code ? (
        <Alert variant="destructive">
          <p className="font-medium">{t(`run.error.${run.error_code}`)}</p>
          {run.error_message ? (
            <p className="mt-1 break-words font-mono text-xs" lang="en">
              {run.error_message}
            </p>
          ) : null}
          {recovery.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2" data-testid="recovery-actions">
              {recovery.map((a) =>
                a.kind === "resume" ? (
                  <ResumeDialog key="resume" run={run} label={t("run.recovery.resume")} />
                ) : a.kind === "checkpoints" ? (
                  <Button
                    key="checkpoints"
                    variant="outline"
                    onClick={() => {
                      setParams({ tab: "checkpoints" }, { replace: true });
                    }}
                  >
                    {t("run.recovery.checkpoints")}
                  </Button>
                ) : (
                  <Button
                    key={a.kind === "clone" ? a.adjust : a.kind}
                    variant="outline"
                    onClick={() => {
                      navigate(path(cloneHref(run.id, a)));
                    }}
                  >
                    <PxIcon name="copy" />
                    {a.kind === "clone"
                      ? t(`run.recovery.${a.adjust}`)
                      : a.kind === "clone_gpu"
                        ? t("run.recovery.clone_gpu", {
                            gpu: gpus.data?.items.find((g) => g.id === a.gpu)?.name ?? a.gpu,
                          })
                        : t("run.recovery.clone_edit")}
                  </Button>
                ),
              )}
            </div>
          ) : null}
        </Alert>
      ) : null}
      {run.mixed_precision_effective && run.mixed_precision_effective !== run.mixed_precision_requested ? (
        <Alert variant="warning">
          {t("run.mixed_precision_forced", {
            requested: run.mixed_precision_requested,
            effective: run.mixed_precision_effective,
          })}
        </Alert>
      ) : null}
      {stream.notices.length > 0 ? (
        <ul className="space-y-1" aria-label={t("run.notices")}>
          {stream.notices.slice(-3).map((n, i) => (
            <li key={`${n.ts}-${i}`}>
              <Alert variant={n.kind === "error" ? "destructive" : "warning"}>
                <span className="flex items-center gap-2">
                  <PxIcon name="warning" />
                  {t(n.kind === "error" ? `run.error.${n.code}` : `run.warning.${n.code}`, {
                    ...(n.params ?? {}),
                    defaultValue: n.message,
                  })}
                </span>
              </Alert>
            </li>
          ))}
        </ul>
      ) : null}
      <Card>
        <CardContent className="flex flex-col gap-4 pt-3 sm:flex-row sm:items-start sm:pt-4">
          <div className="flex shrink-0 items-center gap-3 sm:w-32 sm:flex-col sm:text-center">
            <Mascot mood={mood} />
            <p className="text-sm text-muted-foreground" data-testid="run-hibi">
              {t(`hibi.${mood}`)}
            </p>
          </div>
          <div className="min-w-0 flex-1 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="tabular-nums text-xl">
                {t("run.step_of", {
                  step: formatInt(p.current_step, lng),
                  total: formatInt(p.total_steps, lng),
                })}{" "}
                ({formatNumber(progressPct(run), lng, 3)}%)
              </span>
              <span className="flex items-center gap-1 text-muted-foreground" aria-live="polite">
                {live ? (
                  stream.connection === "open" ? (
                    <>
                      <PxIcon name="wifi" className="text-success" />
                      {t("run.live")}
                    </>
                  ) : (
                    <>
                      <PxIcon name="wifi_off" />
                      {t(`run.connection.${stream.connection}`)}
                    </>
                  )
                ) : null}
              </span>
            </div>
            <Progress value={progressPct(run)} aria-label={t("runs.progress_of", { name: run.name })} />
            <KeyValue
              items={[
                // Speed / ETA / next checkpoint only mean something while the run can still
                // progress (CX-11: finished runs showed a stale "next checkpoint 5000").
                ...(terminal
                  ? []
                  : ([
                      [
                        t("run.speed"),
                        p.steps_per_s
                          ? t("run.steps_per_s", { v: formatNumber(p.steps_per_s, lng, 3) })
                          : "—",
                      ],
                      [t("run.eta"), formatDuration(p.eta_s, lng)],
                      [
                        t("run.next_checkpoint"),
                        p.next_checkpoint_step ? formatInt(p.next_checkpoint_step, lng) : "—",
                      ],
                    ] as [string, string][])),
                ...(terminal && p.last_checkpoint_step
                  ? ([[t("run.last_checkpoint"), formatInt(p.last_checkpoint_step, lng)]] as [
                      string,
                      string,
                    ][])
                  : []),
                [
                  t("run.gpu"),
                  run.gpu_id ??
                    (run.queue_position
                      ? t("runs.queue_position", { pos: run.queue_position })
                      : (run.requested_gpu ?? "—")),
                ],
                [
                  t("wizard.mixed_precision"),
                  run.mixed_precision_effective ?? run.mixed_precision_requested ?? "—",
                ],
                [t("run.attempt"), formatInt(run.attempt, lng)],
                [t("run.gpu_time"), formatDuration(run.gpu_seconds, lng)],
                [t("run.loss"), formatNumber(run.latest_metrics?.loss ?? null, lng)],
                ...(mae !== null ? ([[t("models.mae"), formatNumber(mae, lng)]] as [string, string][]) : []),
                [
                  t("run.model"),
                  run.model_id ? (
                    <Link
                      key="m"
                      className="text-primary hover:underline"
                      to={path(`models/${run.model_id}`)}
                    >
                      {t("run.open_model")}
                    </Link>
                  ) : (
                    "—"
                  ),
                ],
              ]}
            />
            {mae !== null ? (
              <p className="text-xs text-muted-foreground" data-testid="mae-disclaimer">
                {t("eval.offline_not_success_rate")}
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>
      <Tabs
        className="min-w-0 max-w-full"
        value={tab}
        onValueChange={(v) => {
          setParams({ tab: v }, { replace: true });
        }}
      >
        <TabsList>
          {(["metrics", "logs", "gpu", "checkpoints", "config"] as const).map((x) => (
            <TabsTrigger key={x} value={x}>
              {t(`run.tab.${x}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="metrics">
          <MetricsTab stream={stream} />
        </TabsContent>
        <TabsContent value="logs">
          <LogViewer
            runId={run.id}
            lines={stream.logs}
            firstOffset={stream.firstLogOffset}
            terminal={terminal}
          />
        </TabsContent>
        <TabsContent value="gpu">
          <TelemetryTab stream={stream} />
        </TabsContent>
        <TabsContent value="checkpoints">
          <CheckpointsTab run={run} />
        </TabsContent>
        <TabsContent value="config">
          <ConfigTab run={run} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
