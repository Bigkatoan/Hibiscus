import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { Schemas } from "@/api/client";
import { useCompareRuns } from "@/api/hooks/runs";
import { LineChart } from "@/components/charts/LineChart";
import type { XYSeries } from "@/components/charts/series";
import { ErrorAlert, PageHeader, PageLoader } from "@/components/common";
import { RunStatusBadge } from "@/components/StatusBadge";
import { Input } from "@/components/ui/input";
import { Alert, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { useWsPath } from "@/features/workspace/context";

const KEY_RE = /^[a-z][a-z0-9_]{0,63}$/;

/** Overlay one metric key across runs: one series per run. */
export function compareSeries(cmp: Schemas["RunComparison"], key: string): XYSeries[] {
  return cmp.series.flatMap((set) => {
    const run = cmp.runs.find((r) => r.id === set.run_id);
    const s = set.series.find((x) => x.key === key);
    if (!s) return [];
    return [{ label: run ? `#${run.number} ${run.name}` : set.run_id.slice(0, 8), x: s.steps, y: s.values }];
  });
}

/** compareRuns: overlay loss curves + config diff. */
export function ComparePage() {
  const { t } = useTranslation();
  const path = useWsPath();
  const [params, setParams] = useSearchParams();
  const ids = (params.get("ids") ?? "").split(",").filter(Boolean);
  const keys = (params.get("keys") ?? "loss").split(",").filter((k) => KEY_RE.test(k));
  const [keyText, setKeyText] = useState(keys.join(", "));
  const cmp = useCompareRuns(ids, keys);
  const charts = useMemo(
    () => (cmp.data ? keys.map((k) => ({ key: k, series: compareSeries(cmp.data, k) })) : []),
    [cmp.data, keys],
  );

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title={t("compare.title")} description={t("compare.description")} />
      {ids.length < 2 || ids.length > 8 ? <Alert variant="warning">{t("compare.select_range")}</Alert> : null}
      <form
        className="flex max-w-lg items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const next = keyText
            .split(",")
            .map((k) => k.trim())
            .filter((k) => KEY_RE.test(k));
          setParams({ ids: ids.join(","), keys: (next.length ? next : ["loss"]).join(",") });
        }}
      >
        <label className="flex-1 space-y-1 text-sm">
          <span className="block font-medium">{t("compare.keys")}</span>
          <Input
            value={keyText}
            onChange={(e) => {
              setKeyText(e.target.value);
            }}
            placeholder="loss, grad_norm, lr"
          />
        </label>
        <button type="submit" className="h-10 rounded-md border px-4 text-sm hover:bg-accent">
          {t("common.apply")}
        </button>
      </form>
      {cmp.isLoading ? <PageLoader /> : null}
      <ErrorAlert error={cmp.error} />
      {cmp.data ? (
        <>
          <div className="grid gap-6 xl:grid-cols-2">
            {charts.map((c) => (
              <LineChart
                key={c.key}
                title={c.key}
                series={c.series}
                xLabel={t("run.step")}
                syncKey="compare"
              />
            ))}
          </div>
          <section>
            <h2 className="mb-2 font-extrabold text-xl">{t("compare.runs")}</h2>
            <div className="flex flex-wrap gap-3">
              {cmp.data.runs.map((r) => (
                <Link
                  key={r.id}
                  to={path(`runs/${r.id}`)}
                  className="flex items-center gap-2 rounded border px-3 py-2 text-sm hover:bg-accent"
                >
                  #{r.number} {r.name} <RunStatusBadge status={r.status} />
                </Link>
              ))}
            </div>
          </section>
          <section>
            <h2 className="mb-2 font-extrabold text-xl">{t("compare.config_diff")}</h2>
            {cmp.data.config_diff.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("compare.no_diff")}</p>
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>{t("compare.path")}</TH>
                    {cmp.data.runs.map((r) => (
                      <TH key={r.id}>#{r.number}</TH>
                    ))}
                  </TR>
                </THead>
                <TBody>
                  {cmp.data.config_diff.map((d) => (
                    <TR key={d.path}>
                      <TD>
                        <code className="text-xs">{d.path}</code>
                      </TD>
                      {d.values.map((v, i) => (
                        <TD key={i}>
                          <code className="text-xs">{JSON.stringify(v)}</code>
                        </TD>
                      ))}
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
