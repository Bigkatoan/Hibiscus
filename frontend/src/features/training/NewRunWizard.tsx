import { PxIcon } from "@/hibiscus/PixelAnim";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { Schemas } from "@/api/client";
import { useDatasetVersion, useDatasetVersions, useDatasets } from "@/api/hooks/datasets";
import { useModels } from "@/api/hooks/models";
import { useCloneRun, useCreateRun, usePolicies, usePolicy, usePreflight, useRun } from "@/api/hooks/runs";
import { useGpus } from "@/api/hooks/workspaces";
import { ErrorAlert, KeyValue, PageHeader, PageLoader } from "@/components/common";
import { Field } from "@/components/Field";
import { VersionStatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input, NativeSelect } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkspace, useWsPath } from "@/features/workspace/context";
import { formatBytes, formatDuration, formatInt, formatNumber } from "@/lib/format";
import { cn, isRecord } from "@/lib/utils";
import { applyCloneAdjust } from "@/features/runs/recovery";
import { SchemaForm } from "./SchemaForm";
import {
  asSchema,
  buildRequestConfig,
  deepMerge,
  followLogFreq,
  groupFields,
  issuesByField,
  presetBase,
  validateValues,
  type ConfigBase,
} from "./schema";

type S = Schemas;
type PresetId = "quick" | "standard" | "finetune";
const STEPS = ["dataset", "policy", "params", "review"] as const;
type Step = (typeof STEPS)[number];

function Stepper({ step }: { step: Step }) {
  const { t } = useTranslation();
  const idx = STEPS.indexOf(step);
  return (
    // Mobile (CX-10): other steps collapse to their number; the current step shows its full name
    // plus "n/4". From sm up all four labels fit.
    <ol className="mb-6 flex gap-2 sm:grid sm:grid-cols-4" aria-label={t("wizard.progress")}>
      {STEPS.map((s, i) => (
        <li
          key={s}
          aria-current={s === step ? "step" : undefined}
          className={cn(
            "flex items-center gap-2 rounded-md border px-2 py-2 text-xs sm:text-sm",
            s === step ? "min-w-0 flex-1" : "shrink-0",
            i < idx && "border-success/50",
            s === step && "border-primary bg-primary/5 font-semibold",
          )}
        >
          <span
            className={cn(
              "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs",
              i < idx && "bg-success text-success-foreground",
              s === step && "bg-primary text-primary-foreground",
            )}
          >
            {i < idx ? <PxIcon name="check" /> : i + 1}
          </span>
          <span className={cn("min-w-0 sm:truncate", s !== step && "sr-only sm:not-sr-only")}>
            {t(`wizard.step.${s}`)}
          </span>
          {s === step ? (
            <span className="ml-auto shrink-0 font-normal text-muted-foreground sm:hidden">
              {t("wizard.step_n_of", { n: i + 1, total: STEPS.length })}
            </span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function DatasetStep({ versionId, onSelect }: { versionId: string | null; onSelect: (id: string) => void }) {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const datasets = useDatasets(ws.workspace_id, "");
  const current = useDatasetVersion(versionId);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const effectiveDataset = datasetId ?? current.data?.dataset_id ?? null;
  const versions = useDatasetVersions(effectiveDataset ?? "");
  const items = datasets.data?.pages.flatMap((p) => p.items) ?? [];
  if (datasets.isPending) return <PageLoader />;
  return (
    <div className="space-y-4">
      <Field label={t("wizard.dataset")} required>
        <NativeSelect
          value={effectiveDataset ?? ""}
          onChange={(e) => {
            setDatasetId(e.target.value);
            const d = items.find((x) => x.id === e.target.value);
            if (d?.latest_version?.status === "ready") onSelect(d.latest_version.id);
          }}
        >
          <option value="" disabled>
            {t("wizard.choose_dataset")}
          </option>
          {items.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </NativeSelect>
      </Field>
      {effectiveDataset && versions.data ? (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">{t("wizard.version")}</legend>
          {versions.data.items.map((v) => (
            <label
              key={v.id}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-md border p-3 text-sm",
                v.id === versionId && "border-primary bg-primary/5",
                v.status !== "ready" && "cursor-not-allowed opacity-60",
              )}
            >
              <input
                type="radio"
                name="dataset-version"
                value={v.id}
                checked={v.id === versionId}
                disabled={v.status !== "ready"}
                onChange={() => {
                  onSelect(v.id);
                }}
              />
              <span className="font-medium">v{v.version}</span>
              <VersionStatusBadge status={v.status} />
              <span className="text-muted-foreground">
                {t("wizard.version_summary", {
                  episodes: formatInt(v.total_episodes, i18n.language),
                  frames: formatInt(v.total_frames, i18n.language),
                  size: formatBytes(v.size_bytes, i18n.language),
                })}
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}
      {current.data ? (
        <Card>
          <CardContent className="pt-6">
            <KeyValue
              items={[
                [t("datasets.cameras"), current.data.camera_keys.join(", ") || "—"],
                [t("datasets.state_dim"), `${current.data.state_dim ?? "—"}`],
                [t("datasets.action_dim"), `${current.data.action_dim ?? "—"}`],
                [t("datasets.fps"), formatNumber(current.data.fps, i18n.language)],
              ]}
            />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function PolicyStep({
  selected,
  onSelect,
  version,
}: {
  selected: S["PolicyType"] | null;
  onSelect: (p: S["PolicyType"]) => void;
  version: S["DatasetVersion"] | undefined;
}) {
  const { t } = useTranslation();
  const policies = usePolicies();
  if (policies.isPending) return <PageLoader />;
  if (policies.isError) return <ErrorAlert error={policies.error} />;
  const hasReward = !!version?.features && "next.reward" in version.features;
  return (
    <fieldset>
      <legend className="sr-only">{t("wizard.step.policy")}</legend>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {policies.data.items.map((p) => {
          const blocked = !p.trainable || (p.requires_reward && !hasReward);
          return (
            <label
              key={p.type}
              className={cn(
                "flex cursor-pointer flex-col gap-2 rounded-lg border p-4 text-sm transition-colors hover:bg-accent/50",
                selected === p.type && "border-primary bg-primary/5 ring-1 ring-primary",
                blocked && "cursor-not-allowed opacity-60",
              )}
            >
              <span className="flex items-center gap-2">
                <input
                  type="radio"
                  name="policy"
                  value={p.type}
                  checked={selected === p.type}
                  disabled={blocked}
                  onChange={() => {
                    onSelect(p.type);
                  }}
                />
                <span className="text-base font-semibold">{p.display_name}</span>
                {p.experimental ? <Badge variant="warning">{t("policy.experimental")}</Badge> : null}
              </span>
              <span className="text-muted-foreground">{t(`policy.summary.${p.type}`)}</span>
              <span className="flex flex-wrap gap-1">
                <Badge variant={p.onnx === "none" ? "outline" : "secondary"}>
                  {t(`policy.onnx.${p.onnx}`)}
                </Badge>
                {p.requires_peft ? <Badge variant="outline">{t("policy.requires_peft")}</Badge> : null}
                {p.requires_language ? (
                  <Badge variant="outline">{t("policy.requires_language")}</Badge>
                ) : null}
                {p.requires_reward ? <Badge variant="outline">{t("policy.requires_reward")}</Badge> : null}
              </span>
              <span className="flex flex-wrap gap-2 text-xs">
                {Object.entries(p.gpu_support).map(([gpu, lvl]) => (
                  <span key={gpu} className="inline-flex items-center gap-1">
                    <PxIcon name="chip" />
                    {gpu}: {t(`policy.gpu_support.${lvl}`)}
                  </span>
                ))}
              </span>
              {p.onnx === "none" && p.onnx_reason_key ? (
                <span className="text-xs text-muted-foreground">{t(p.onnx_reason_key)}</span>
              ) : null}
              {p.requires_reward && !hasReward ? (
                <span className="text-xs text-destructive">{t("policy.reward_missing")}</span>
              ) : null}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export interface RunSettings {
  name: string;
  heldoutPct: number;
  gpu: string;
  seed: string;
  exportOnnx: boolean;
  exportFp16: boolean;
  exportEval: boolean;
  initModelId: string;
  initHfRepo: string;
}

function SettingsCard({
  settings,
  onChange,
  needsInit,
}: {
  settings: RunSettings;
  onChange: (s: RunSettings) => void;
  needsInit: boolean;
}) {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const gpus = useGpus(false);
  const models = useModels(ws.workspace_id, { verified: true });
  const set = <K extends keyof RunSettings>(k: K, v: RunSettings[K]) => {
    onChange({ ...settings, [k]: v });
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("wizard.run_settings")}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <Field label={t("wizard.run_name")} description={t("wizard.run_name_help")}>
          <Input
            value={settings.name}
            maxLength={100}
            onChange={(e) => {
              set("name", e.target.value);
            }}
          />
        </Field>
        <Field label={t("wizard.gpu")} description={t("wizard.gpu_help")}>
          <NativeSelect
            value={settings.gpu}
            onChange={(e) => {
              set("gpu", e.target.value);
            }}
          >
            <option value="auto">{t("gpu.auto")}</option>
            {(gpus.data?.items ?? []).map((g) => (
              <option key={g.id} value={g.id} disabled={g.status === "disabled" || g.status === "offline"}>
                {g.id} · {g.name} ({formatNumber(g.total_vram_mb / 1024, i18n.language)} GB)
                {g.supports_bf16 ? "" : ` · ${t("gpu.no_bf16")}`}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label={t("wizard.heldout")} description={t("wizard.heldout_help")}>
          <Input
            type="number"
            min={0}
            max={50}
            step={1}
            value={settings.heldoutPct}
            onChange={(e) => {
              set("heldoutPct", Number(e.target.value));
            }}
          />
        </Field>
        <Field label={t("wizard.seed")} description={t("wizard.seed_help")}>
          <Input
            type="number"
            value={settings.seed}
            onChange={(e) => {
              set("seed", e.target.value);
            }}
          />
        </Field>
        <fieldset className="space-y-2 md:col-span-2">
          <legend className="text-sm font-medium">{t("wizard.export")}</legend>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={settings.exportOnnx}
              onChange={(e) => {
                set("exportOnnx", e.target.checked);
              }}
            />
            {t("wizard.export_onnx")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={settings.exportFp16}
              disabled={!settings.exportOnnx}
              onChange={(e) => {
                set("exportFp16", e.target.checked);
              }}
            />
            {t("wizard.export_fp16")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={settings.exportEval}
              onChange={(e) => {
                set("exportEval", e.target.checked);
              }}
            />
            {t("wizard.export_eval")}
          </label>
        </fieldset>
        {needsInit ? (
          <div className="grid gap-4 md:col-span-2 md:grid-cols-2">
            <Field label={t("wizard.init_model")} description={t("wizard.init_help")}>
              <NativeSelect
                value={settings.initModelId}
                onChange={(e) => {
                  set("initModelId", e.target.value);
                }}
              >
                <option value="">—</option>
                {(models.data?.pages.flatMap((p) => p.items) ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} (#{m.run_number}, {t("models.step", { step: formatInt(m.step, i18n.language) })})
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label={t("wizard.init_hf")}>
              <Input
                placeholder="lerobot/smolvla_base"
                value={settings.initHfRepo}
                onChange={(e) => {
                  set("initHfRepo", e.target.value);
                }}
              />
            </Field>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function PreflightView({ report }: { report: S["PreflightReport"] }) {
  const { t, i18n } = useTranslation();
  const e = report.estimate;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("wizard.estimate")}</CardTitle>
          <CardDescription>{t(`wizard.estimate_source.${e.source}`)}</CardDescription>
        </CardHeader>
        <CardContent>
          <KeyValue
            items={[
              [t("wizard.gpu"), report.resolved.gpu_id ?? t("gpu.auto")],
              [t("wizard.mixed_precision"), report.resolved.mixed_precision],
              [
                t("wizard.peak_vram"),
                e.peak_vram_mb !== null && e.peak_vram_mb !== undefined
                  ? formatBytes(e.peak_vram_mb * 1024 * 1024, i18n.language)
                  : "—",
              ],
              [t("wizard.sec_per_step"), formatNumber(e.sec_per_step, i18n.language, 3)],
              [t("wizard.total_time"), formatDuration(e.total_duration_s, i18n.language)],
              [
                t("wizard.split"),
                t("wizard.split_value", {
                  train: report.resolved.train_episodes.length,
                  heldout: report.resolved.heldout_episodes.length,
                }),
              ],
            ]}
          />
        </CardContent>
      </Card>
      <ul className="space-y-2" aria-label={t("wizard.checks")}>
        {report.checks.map((c, i) => {
          const glyph = c.severity === "error" ? "close" : c.severity === "warning" ? "warning" : "info";
          return (
            <li key={`${c.id}-${i}`} className="flex gap-2 rounded-md border p-3 text-sm">
              <PxIcon
                name={glyph}
                className={cn(
                  "mt-0.5 shrink-0",
                  c.severity === "error"
                    ? "text-destructive"
                    : c.severity === "warning"
                      ? "text-warning"
                      : "text-muted-foreground",
                )}
              />
              <div>
                <p className="font-medium">{t(`preflight.check.${c.id}`)}</p>
                <p className="text-muted-foreground">
                  {t([`preflight.code.${c.code}`, `errors.${c.code}`, `run.warning.${c.code}`], {
                    ...(c.params ?? {}),
                    defaultValue: c.message,
                  })}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
      <details className="rounded-md border p-3 text-sm">
        <summary className="cursor-pointer font-medium">{t("wizard.lerobot_args")}</summary>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all rounded bg-muted p-2 text-xs">
          {report.resolved.lerobot_args.join(" \\\n  ")}
        </pre>
      </details>
    </div>
  );
}

const DEFAULT_SETTINGS: RunSettings = {
  name: "",
  heldoutPct: 10,
  gpu: "auto",
  seed: "",
  exportOnnx: true,
  exportFp16: false,
  exportEval: true,
  initModelId: "",
  initHfRepo: "",
};

/** 4-step training wizard: dataset -> policy -> hyperparameters -> review (preflight) -> createRun. */
export function NewRunWizard() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const path = useWsPath();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const cloneId = params.get("clone");
  // Failed-run recovery buttons (CX-06): ?adjust=half_batch|lower_lr, ?gpu=<id>.
  const adjust = params.get("adjust");
  const gpuParam = params.get("gpu");
  const [adjusted, setAdjusted] = useState<{ field: string; from: number; to: number } | null>(null);
  const cloneSource = useRun(cloneId ?? "");
  const [step, setStep] = useState<Step>(params.get("version") ? "policy" : "dataset");
  const [versionId, setVersionId] = useState<string | null>(params.get("version"));
  // ACT is the golden path (PLAN §6: upload -> train in <= 5 clicks: Start upload, Train now,
  // Next, Review, Start training).
  const [policyType, setPolicyType] = useState<S["PolicyType"] | null>("act");
  const [presetId, setPresetId] = useState<PresetId>("quick");
  const [values, setValues] = useState<ConfigBase | null>(null);
  const [settings, setSettings] = useState<RunSettings>(DEFAULT_SETTINGS);
  const [showAdvanced, setShowAdvanced] = useState<"basic" | "advanced">("basic");
  const version = useDatasetVersion(versionId);
  const policy = usePolicy(policyType);
  const preflight = usePreflight();
  const create = useCreateRun();
  const clone = useCloneRun();

  // Clone mode: prefill everything from the source run (cloneRun).
  const src = cloneId ? cloneSource.data : undefined;
  useEffect(() => {
    if (!src) return;
    setVersionId(src.dataset_version_id);
    setPolicyType(src.policy_type);
    if (src.preset === "quick" || src.preset === "standard" || src.preset === "finetune")
      setPresetId(src.preset);
    setSettings((s) => ({
      ...s,
      name: `${src.name}-clone`,
      gpu: gpuParam ?? src.requested_gpu ?? "auto",
    }));
    setStep("params");
  }, [src, gpuParam]);

  const policySchema = useMemo(() => asSchema(policy.data?.policy_schema), [policy.data]);
  const trainSchema = useMemo(() => asSchema(policy.data?.train_schema), [policy.data]);
  const preset = policy.data?.presets.find((p) => p.id === presetId) ?? null;
  const base = useMemo(
    () => (policy.data ? presetBase(policySchema, trainSchema, preset) : null),
    [policy.data, policySchema, trainSchema, preset],
  );

  // Reset form values whenever policy or preset changes (clone keeps its config once).
  useEffect(() => {
    if (!base) return;
    if (src?.policy_type === policyType && values === null) {
      const cloned = {
        policy: deepMerge(base.policy, isRecord(src.config.policy) ? src.config.policy : {}),
        train: deepMerge(base.train, isRecord(src.config.train) ? src.config.train : {}),
      };
      const { changed, ...next } = applyCloneAdjust(cloned, adjust);
      setAdjusted(changed);
      setValues(next as ConfigBase);
      return;
    }
    setValues({ policy: { ...base.policy }, train: { ...base.train } });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  const policyIssues = useMemo(
    () => (values ? issuesByField(validateValues(values.policy, policySchema)) : new Map()),
    [values, policySchema],
  );
  const trainIssues = useMemo(
    () => (values ? issuesByField(validateValues(values.train, trainSchema)) : new Map()),
    [values, trainSchema],
  );
  const policyGroups = useMemo(() => groupFields(policySchema), [policySchema]);
  const trainGroups = useMemo(() => groupFields(trainSchema), [trainSchema]);
  const needsInit = !!preset?.requires_init_from;
  const initFrom: S["InitFrom"] | null = settings.initModelId
    ? { model_id: settings.initModelId }
    : settings.initHfRepo.trim()
      ? { hf_repo_id: settings.initHfRepo.trim() }
      : null;

  const buildRequest = (): S["RunCreate"] | null => {
    if (!values || !base || !policyType || !versionId) return null;
    const config = buildRequestConfig(values, base, policySchema, trainSchema);
    const seed = settings.seed.trim() === "" ? null : Number(settings.seed);
    return {
      workspace_id: ws.workspace_id,
      dataset_version_id: versionId,
      policy_type: policyType,
      preset: presetId,
      config,
      heldout_fraction: Math.max(0, Math.min(50, settings.heldoutPct)) / 100,
      gpu: settings.gpu,
      export: {
        onnx: settings.exportOnnx,
        onnx_fp16: settings.exportOnnx && settings.exportFp16,
        eval: settings.exportEval,
      },
      seed,
      ...(settings.name.trim() ? { name: settings.name.trim() } : {}),
      ...(initFrom ? { init_from: initFrom } : {}),
    };
  };

  const goReview = () => {
    const req = buildRequest();
    if (!req) return;
    setStep("review");
    preflight.mutate(req);
  };

  const submit = async () => {
    const req = buildRequest();
    if (!req) return;
    const run =
      cloneId && src
        ? await clone.mutateAsync({
            id: cloneId,
            body: {
              dataset_version_id: req.dataset_version_id,
              config: req.config,
              ...(req.heldout_fraction !== undefined ? { heldout_fraction: req.heldout_fraction } : {}),
              ...(req.gpu ? { gpu: req.gpu } : {}),
              ...(req.name ? { name: req.name } : {}),
              ...(req.export ? { export: req.export } : {}),
              init_from: req.init_from ?? null,
            },
          })
        : await create.mutateAsync(req);
    navigate(path(`runs/${run.id}`));
  };

  const hasErrors = policyIssues.size > 0 || trainIssues.size > 0 || (needsInit && !initFrom);
  const submitting = create.isPending || clone.isPending;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title={cloneId ? t("wizard.clone_title", { name: src?.name ?? "" }) : t("wizard.title")}
        description={t("wizard.description")}
      />
      <Stepper step={step} />
      {step === "dataset" ? <DatasetStep versionId={versionId} onSelect={setVersionId} /> : null}
      {step === "policy" ? (
        <PolicyStep selected={policyType} onSelect={setPolicyType} version={version.data} />
      ) : null}
      {step === "params" ? (
        policy.isPending || !values || !base ? (
          <PageLoader />
        ) : (
          <div className="space-y-6">
            {adjusted ? (
              <Alert variant="success" data-testid="clone-adjusted">
                {t("wizard.adjusted", {
                  field: t(
                    adjusted.field === "batch_size"
                      ? "train.batch_size.label"
                      : `policy.${policyType ?? ""}.${adjusted.field}.label`,
                    { defaultValue: adjusted.field },
                  ),
                  from: formatNumber(adjusted.from, i18n.language),
                  to: formatNumber(adjusted.to, i18n.language),
                })}
              </Alert>
            ) : null}
            <fieldset>
              <legend className="mb-2 text-sm font-medium">{t("wizard.preset")}</legend>
              <div className="flex flex-wrap gap-2">
                {(policy.data?.presets ?? []).map((p) => (
                  <label
                    key={p.id}
                    className={cn(
                      "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm",
                      presetId === p.id && "border-primary bg-primary/5",
                    )}
                  >
                    <input
                      type="radio"
                      name="preset"
                      value={p.id}
                      checked={presetId === p.id}
                      onChange={() => {
                        setPresetId(p.id);
                      }}
                    />
                    {t(p.label_key)}
                  </label>
                ))}
              </div>
            </fieldset>
            <Tabs
              value={showAdvanced}
              onValueChange={(v) => {
                setShowAdvanced(v === "advanced" ? "advanced" : "basic");
              }}
            >
              <TabsList>
                <TabsTrigger value="basic">{t("wizard.basic")}</TabsTrigger>
                <TabsTrigger value="advanced">{t("wizard.advanced")}</TabsTrigger>
              </TabsList>
              {(["basic", "advanced"] as const).map((g) => (
                <TabsContent key={g} value={g} className="space-y-6">
                  <section aria-labelledby={`train-${g}`}>
                    <h2 id={`train-${g}`} className="mb-3 font-extrabold text-xl">
                      {t("wizard.training_section")}
                    </h2>
                    <SchemaForm
                      fields={trainGroups[g]}
                      values={values.train}
                      base={base.train}
                      issues={trainIssues}
                      labelPrefix="train"
                      onChange={(train) => {
                        setValues({ ...values, train: followLogFreq(values.train, train, base.train) });
                      }}
                    />
                  </section>
                  <section aria-labelledby={`policy-${g}`}>
                    <h2 id={`policy-${g}`} className="mb-3 font-extrabold text-xl">
                      {t("wizard.policy_section", { policy: policy.data?.display_name ?? "" })}
                    </h2>
                    <SchemaForm
                      fields={policyGroups[g]}
                      values={values.policy}
                      base={base.policy}
                      issues={policyIssues}
                      labelPrefix={`policy.${policyType ?? ""}`}
                      onChange={(p) => {
                        setValues({ ...values, policy: p });
                      }}
                    />
                  </section>
                </TabsContent>
              ))}
            </Tabs>
            <SettingsCard settings={settings} onChange={setSettings} needsInit={needsInit} />
            {needsInit && !initFrom ? <Alert variant="warning">{t("wizard.init_required")}</Alert> : null}
            {hasErrors && (policyIssues.size > 0 || trainIssues.size > 0) ? (
              <Alert variant="destructive">{t("wizard.fix_errors")}</Alert>
            ) : null}
          </div>
        )
      ) : null}
      {step === "review" ? (
        <div className="space-y-4">
          {preflight.isPending ? <PageLoader /> : null}
          <ErrorAlert error={preflight.error} />
          {preflight.data ? <PreflightView report={preflight.data} /> : null}
          {preflight.data && !preflight.data.ok ? (
            <Alert variant="destructive">{t("wizard.preflight_blocked")}</Alert>
          ) : null}
          <ErrorAlert error={create.error ?? clone.error} />
        </div>
      ) : null}
      <div className="mt-8 flex justify-between gap-2">
        <Button
          variant="outline"
          disabled={step === "dataset"}
          onClick={() => {
            setStep(STEPS[Math.max(0, STEPS.indexOf(step) - 1)] ?? "dataset");
          }}
        >
          <PxIcon name="chevron_left" />
          {t("common.back")}
        </Button>
        {step === "dataset" ? (
          <Button
            disabled={!versionId || version.data?.status !== "ready"}
            onClick={() => {
              setStep("policy");
            }}
          >
            {t("common.next")}
            <PxIcon name="chevron_right" />
          </Button>
        ) : null}
        {step === "policy" ? (
          <Button
            disabled={!policyType}
            onClick={() => {
              setStep("params");
            }}
          >
            {t("common.next")}
            <PxIcon name="chevron_right" />
          </Button>
        ) : null}
        {step === "params" ? (
          <Button disabled={!values || hasErrors} onClick={goReview}>
            {t("wizard.review")}
            <PxIcon name="chevron_right" />
          </Button>
        ) : null}
        {step === "review" ? (
          <Button
            disabled={!preflight.data?.ok || submitting}
            onClick={() => void submit().catch(() => undefined)}
          >
            {submitting ? <PxIcon name="spinner" className="px-spin" /> : <PxIcon name="sprout" />}
            {t("wizard.start")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
