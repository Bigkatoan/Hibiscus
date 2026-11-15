/**
 * Suggested recovery actions for a failed run (user guide §4.8, UAT-45, CX-06). Pure so it can be
 * unit tested; RunDetailPage renders one button per action.
 */
import type { Schemas } from "@/api/client";

type S = Schemas;

/** Adjustments the wizard applies to a cloned config (`/runs/new?clone=<id>&adjust=<id>`). */
export type CloneAdjust = "half_batch" | "lower_lr";

export type RecoveryAction =
  | { kind: "clone"; adjust: CloneAdjust }
  | { kind: "clone_gpu"; gpu: string }
  | { kind: "clone_edit" }
  | { kind: "resume" }
  | { kind: "checkpoints" };

const RESUMABLE: readonly string[] = [
  "worker_lost",
  "gpu_error",
  "stalled",
  "process_crashed",
  "internal_error",
  "dataset_unavailable",
  "storage_error",
  "checkpoint_corrupt",
  "quota_exceeded",
];

export function recoveryActions(
  run: Pick<S["Run"], "error_code" | "allowed_actions" | "gpu_id">,
  gpus: readonly Pick<S["GpuNode"], "id" | "name" | "status">[] = [],
): RecoveryAction[] {
  const code = run.error_code;
  if (!code) return [];
  const allowed = new Set(run.allowed_actions ?? []);
  const out: RecoveryAction[] = [];
  const canClone = allowed.has("clone");
  switch (code) {
    case "oom": {
      if (canClone) out.push({ kind: "clone", adjust: "half_batch" });
      // Guide: "or choose the Tesla P40" (24 GB). Offer any other usable GPU with more memory.
      const p40 = gpus.find(
        (g) =>
          /p40/i.test(g.name) && g.id !== run.gpu_id && g.status !== "disabled" && g.status !== "offline",
      );
      if (canClone && p40) out.push({ kind: "clone_gpu", gpu: p40.id });
      break;
    }
    case "nan_loss":
      if (canClone) out.push({ kind: "clone", adjust: "lower_lr" });
      break;
    case "config_invalid":
    case "dataset_feature_mismatch":
      if (canClone) out.push({ kind: "clone_edit" });
      break;
    case "export_failed":
      out.push({ kind: "checkpoints" });
      break;
    default:
      break;
  }
  if (RESUMABLE.includes(code) && allowed.has("resume")) out.push({ kind: "resume" });
  return out;
}

export function cloneHref(runId: string, action: RecoveryAction): string {
  const q = new URLSearchParams({ clone: runId });
  if (action.kind === "clone") q.set("adjust", action.adjust);
  if (action.kind === "clone_gpu") q.set("gpu", action.gpu);
  return `runs/new?${q.toString()}`;
}

/** Apply a recovery adjustment to cloned values (batch size halved, learning rate / 10). */
export function applyCloneAdjust(
  values: { policy: Record<string, unknown>; train: Record<string, unknown> },
  adjust: string | null,
): {
  policy: Record<string, unknown>;
  train: Record<string, unknown>;
  changed: { field: string; from: number; to: number } | null;
} {
  if (adjust === "half_batch" && typeof values.train.batch_size === "number") {
    const from = values.train.batch_size;
    const to = Math.max(1, Math.floor(from / 2));
    return {
      ...values,
      train: { ...values.train, batch_size: to },
      changed: { field: "batch_size", from, to },
    };
  }
  if (adjust === "lower_lr" && typeof values.policy.optimizer_lr === "number") {
    const from = values.policy.optimizer_lr;
    const to = Number((from / 10).toPrecision(6));
    return {
      ...values,
      policy: { ...values.policy, optimizer_lr: to },
      changed: { field: "optimizer_lr", from, to },
    };
  }
  return { ...values, changed: null };
}
