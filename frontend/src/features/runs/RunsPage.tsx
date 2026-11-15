import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import type { Schemas } from "@/api/client";
import { useRuns, type RunFilters } from "@/api/hooks/runs";
import { EmptyState, ErrorAlert, LoadMore, PageHeader, PageLoader } from "@/components/common";
import { RunStatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox, Input, NativeSelect } from "@/components/ui/input";
import { Progress, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { useCan, useWorkspace, useWsPath } from "@/features/workspace/context";
import { formatDuration, formatInt, formatNumber, formatRelative } from "@/lib/format";

const STATUS_FILTERS: Record<string, Schemas["RunStatus"][] | undefined> = {
  all: undefined,
  active: ["queued", "preparing", "running", "pausing", "exporting", "cancelling"],
  paused: ["paused"],
  succeeded: ["succeeded"],
  failed: ["failed"],
  cancelled: ["cancelled"],
};

export function progressPct(run: Schemas["Run"]): number {
  const { current_step, total_steps } = run.progress;
  return total_steps > 0 ? Math.min(100, (current_step / total_steps) * 100) : 0;
}

/** listRuns with filters; select 2..8 runs to compare. */
export function RunsPage() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const path = useWsPath();
  const navigate = useNavigate();
  const canWrite = useCan("member");
  const [statusKey, setStatusKey] = useState("all");
  const [mine, setMine] = useState(false);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const filters: RunFilters = {
    ...(STATUS_FILTERS[statusKey] ? { status: STATUS_FILTERS[statusKey] } : {}),
    ...(mine ? { created_by: "me" } : {}),
    ...(q.trim() ? { q: q.trim() } : {}),
  };
  const runs = useRuns(ws.workspace_id, filters);
  const items = runs.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title={t("runs.title")}
        description={t("runs.description")}
        actions={
          <>
            <Button
              variant="outline"
              disabled={selected.length < 2 || selected.length > 8}
              onClick={() => navigate(path(`runs/compare?ids=${selected.join(",")}`))}
            >
              <PxIcon name="compare" />
              {t("runs.compare", { count: selected.length })}
            </Button>
            {canWrite ? (
              <Button asChild>
                <Link to={path("runs/new")}>
                  <PxIcon name="plus" />
                  {t("runs.new")}
                </Link>
              </Button>
            ) : null}
          </>
        }
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-sm">
          <span className="block font-medium">{t("common.status")}</span>
          <NativeSelect
            className="w-44"
            value={statusKey}
            onChange={(e) => {
              setStatusKey(e.target.value);
            }}
          >
            {Object.keys(STATUS_FILTERS).map((k) => (
              <option key={k} value={k}>
                {t(`runs.filter.${k}`)}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="space-y-1 text-sm">
          <span className="block font-medium">{t("common.search")}</span>
          <Input
            className="w-56"
            type="search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
            }}
            placeholder={t("runs.search_placeholder")}
          />
        </label>
        <label className="flex items-center gap-2 pb-2 text-sm">
          <Checkbox
            checked={mine}
            onChange={(e) => {
              setMine(e.target.checked);
            }}
          />
          {t("runs.only_mine")}
        </label>
      </div>
      {runs.isPending ? <PageLoader /> : null}
      <ErrorAlert error={runs.error} />
      {runs.isSuccess && items.length === 0 ? (
        <EmptyState
          title={t("runs.empty")}
          description={t("runs.empty_help")}
          action={
            canWrite ? (
              <Button asChild>
                <Link to={path("runs/new")}>{t("runs.new")}</Link>
              </Button>
            ) : undefined
          }
        />
      ) : null}
      {items.length > 0 ? (
        <Table>
          <THead>
            <TR>
              <TH>
                <span className="sr-only">{t("runs.select")}</span>
              </TH>
              <TH>{t("runs.run")}</TH>
              <TH>{t("common.status")}</TH>
              <TH>{t("runs.policy")}</TH>
              <TH>{t("runs.dataset")}</TH>
              <TH className="min-w-[10rem]">{t("runs.progress")}</TH>
              <TH>{t("runs.loss")}</TH>
              <TH>{t("runs.gpu")}</TH>
              <TH>{t("common.created")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((r) => (
              <TR key={r.id}>
                <TD>
                  <Checkbox
                    aria-label={t("runs.select_run", { name: r.name })}
                    checked={selected.includes(r.id)}
                    onChange={(e) => {
                      setSelected((s) => (e.target.checked ? [...s, r.id] : s.filter((x) => x !== r.id)));
                    }}
                  />
                </TD>
                <TD>
                  <Link to={path(`runs/${r.id}`)} className="font-medium text-primary hover:underline">
                    #{r.number} {r.name}
                  </Link>
                  <p className="text-xs text-muted-foreground">{r.created_by.display_name}</p>
                </TD>
                <TD>
                  <RunStatusBadge status={r.status} />
                  {r.status === "queued" && r.queue_position ? (
                    <p className="text-xs text-muted-foreground">
                      {t("runs.queue_position", { pos: r.queue_position })}
                    </p>
                  ) : null}
                </TD>
                <TD className="uppercase">{r.policy_type}</TD>
                <TD>
                  {r.dataset.name} <span className="text-muted-foreground">v{r.dataset.version}</span>
                </TD>
                <TD>
                  <Progress value={progressPct(r)} aria-label={t("runs.progress_of", { name: r.name })} />
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatInt(r.progress.current_step, i18n.language)}/
                    {formatInt(r.progress.total_steps, i18n.language)}
                    {r.progress.eta_s
                      ? ` · ${t("runs.eta", { eta: formatDuration(r.progress.eta_s, i18n.language) })}`
                      : ""}
                  </p>
                </TD>
                <TD>{formatNumber(r.latest_metrics?.loss ?? null, i18n.language)}</TD>
                <TD>{r.gpu_id ?? r.requested_gpu ?? "—"}</TD>
                <TD>{formatRelative(r.created_at, i18n.language)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}
      <LoadMore
        hasNextPage={runs.hasNextPage}
        isFetchingNextPage={runs.isFetchingNextPage}
        fetchNextPage={runs.fetchNextPage}
      />
    </div>
  );
}
