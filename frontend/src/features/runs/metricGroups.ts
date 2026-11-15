import type { XYSeries } from "@/components/charts/series";
import { smooth } from "@/components/charts/series";
import type { SeriesBuf } from "./runStream";

/** Chart grouping of canonical metric keys (docs/spec/log-parsing.md §5). */
export const METRIC_GROUPS: { id: string; keys: (k: string) => boolean; logY?: boolean }[] = [
  { id: "loss", keys: (k) => k === "loss" || k.endsWith("_loss") },
  { id: "grad", keys: (k) => k === "grad_norm" || k === "grad_scale" },
  { id: "lr", keys: (k) => k === "lr" },
  { id: "throughput", keys: (k) => k === "samples_per_s" },
  { id: "timing", keys: (k) => ["data_s", "prep_s", "update_s", "step_s"].includes(k) },
  { id: "memory", keys: (k) => k === "gpu_mem_gb" },
];

const IGNORED = new Set(["epoch"]);

export interface MetricChartSpec {
  id: string;
  series: XYSeries[];
  logY: boolean;
}

export function buildMetricCharts(metrics: Record<string, SeriesBuf>, smoothing = 0): MetricChartSpec[] {
  const keys = Object.keys(metrics)
    .filter((k) => !IGNORED.has(k))
    .sort();
  const used = new Set<string>();
  const charts: MetricChartSpec[] = [];
  for (const g of METRIC_GROUPS) {
    const ks = keys.filter((k) => g.keys(k));
    if (!ks.length) continue;
    ks.forEach((k) => used.add(k));
    charts.push({
      id: g.id,
      logY: !!g.logY,
      series: ks.map((k) => {
        const buf = metrics[k] ?? { steps: [], values: [] };
        return { label: k, x: buf.steps, y: g.id === "loss" ? smooth(buf.values, smoothing) : buf.values };
      }),
    });
  }
  for (const k of keys) {
    if (used.has(k)) continue;
    const buf = metrics[k] ?? { steps: [], values: [] };
    charts.push({ id: `other:${k}`, logY: false, series: [{ label: k, x: buf.steps, y: buf.values }] });
  }
  return charts;
}
