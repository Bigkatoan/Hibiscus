import { PxIcon } from "@/hibiscus/PixelAnim";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Schemas } from "@/api/client";
import { useGpus, useQueue } from "@/api/hooks/workspaces";
import { ErrorAlert, PageHeader, PageLoader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { useOptionalWorkspace, useWorkspace, useWsPath } from "@/features/workspace/context";
import { formatDateTime, formatNumber, formatRelative } from "@/lib/format";

export function GpuCard({ gpu, children }: { gpu: Schemas["GpuNode"]; children?: React.ReactNode }) {
  const { t, i18n } = useTranslation();
  const ws = useOptionalWorkspace();
  const tel = gpu.telemetry;
  const memPct = tel ? (tel.mem_used_mb / Math.max(1, tel.mem_total_mb)) * 100 : 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <PxIcon name="chip" />
          {gpu.id} · {gpu.name}
          <Badge
            variant={gpu.status === "online" ? "success" : gpu.status === "draining" ? "warning" : "outline"}
          >
            {t(`gpu.status.${gpu.status}`)}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          {t("gpu.specs", {
            vram: formatNumber(gpu.total_vram_mb / 1024, i18n.language, 3),
            cc: gpu.compute_capability,
          })}{" "}
          {gpu.supports_bf16 ? (
            <Badge variant="secondary">bf16</Badge>
          ) : (
            <Badge variant="outline">{t("gpu.no_bf16")}</Badge>
          )}
        </p>
        {tel ? (
          <>
            <div>
              <div className="mb-1 flex justify-between">
                <span>{t("gpu.util")}</span>
                <span>{formatNumber(tel.util_pct, i18n.language)} %</span>
              </div>
              <Progress value={tel.util_pct} aria-label={t("gpu.util")} />
            </div>
            <div>
              <div className="mb-1 flex justify-between">
                <span>{t("gpu.memory")}</span>
                <span>
                  {formatNumber(tel.mem_used_mb / 1024, i18n.language, 3)} /{" "}
                  {formatNumber(tel.mem_total_mb / 1024, i18n.language, 3)} GB
                </span>
              </div>
              <Progress value={memPct} aria-label={t("gpu.memory")} />
            </div>
            <p className="text-muted-foreground">
              {formatNumber(tel.temperature_c, i18n.language)} °C · {formatNumber(tel.power_w, i18n.language)}{" "}
              W
            </p>
          </>
        ) : (
          <p className="text-muted-foreground">{t("gpu.no_telemetry")}</p>
        )}
        {gpu.current_run ? (
          <p>
            {t("gpu.running")}{" "}
            {ws && gpu.current_run.workspace_id === ws.workspace_id && gpu.current_run.id ? (
              <Link
                className="text-primary hover:underline"
                to={`/w/${ws.workspace_slug}/runs/${gpu.current_run.id}`}
              >
                {gpu.current_run.name}
              </Link>
            ) : (
              <span>{gpu.current_run.name ?? t("gpu.other_workspace")}</span>
            )}{" "}
            ({gpu.current_run.step ?? 0}/{gpu.current_run.total_steps ?? 0})
          </p>
        ) : (
          <p className="text-muted-foreground">{t("gpu.idle")}</p>
        )}
        {gpu.last_heartbeat_at ? (
          <p className="text-xs text-muted-foreground">
            {t("gpu.heartbeat", { when: formatRelative(gpu.last_heartbeat_at, i18n.language) })}
          </p>
        ) : null}
        {children}
      </CardContent>
    </Card>
  );
}

/** listGpus + getQueue (live GPU telemetry and the fair-share queue). */
export function GpusPage() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const path = useWsPath();
  const gpus = useGpus(5000);
  const queue = useQueue(10_000);
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title={t("gpu.title")} description={t("gpu.description")} />
      {gpus.isPending ? <PageLoader /> : null}
      <ErrorAlert error={gpus.error} />
      <div className="grid gap-4 md:grid-cols-2">
        {gpus.data?.items.map((g) => <GpuCard key={g.id} gpu={g} />)}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t("gpu.queue")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ErrorAlert error={queue.error} />
          {queue.data && queue.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("gpu.queue_empty")}</p>
          ) : null}
          {queue.data && queue.data.items.length > 0 ? (
            <Table>
              <THead>
                <TR>
                  <TH>#</TH>
                  <TH>{t("runs.run")}</TH>
                  <TH>{t("runs.policy")}</TH>
                  <TH>{t("wizard.gpu")}</TH>
                  <TH>{t("gpu.vram_needed")}</TH>
                  <TH>{t("gpu.est_start")}</TH>
                </TR>
              </THead>
              <TBody>
                {queue.data.items.map((q) => (
                  <TR key={`${q.position}-${q.run_id ?? ""}`}>
                    <TD>{q.position}</TD>
                    <TD>
                      {q.run_id && q.workspace_id === ws.workspace_id ? (
                        <Link className="text-primary hover:underline" to={path(`runs/${q.run_id}`)}>
                          {q.run_name}
                        </Link>
                      ) : (
                        (q.run_name ?? t("gpu.other_workspace"))
                      )}
                    </TD>
                    <TD className="uppercase">{q.policy_type}</TD>
                    <TD>{q.requested_gpu}</TD>
                    <TD>
                      {q.required_vram_mb
                        ? `${formatNumber(q.required_vram_mb / 1024, i18n.language, 3)} GB`
                        : "—"}
                    </TD>
                    <TD>{formatDateTime(q.estimated_start_at, i18n.language)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
