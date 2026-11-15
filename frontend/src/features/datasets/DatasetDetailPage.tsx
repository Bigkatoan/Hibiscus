import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiUrl, type Schemas } from "@/api/client";
import {
  isVersionActive,
  useDataset,
  useDatasetPreview,
  useDatasetVersion,
  useDatasetVersions,
  useDeleteDataset,
  useDeleteDatasetVersion,
  useMergeDatasets,
  useRevalidate,
  useValidationReport,
} from "@/api/hooks/datasets";
import { useCancelJob, useJob } from "@/api/hooks/workspaces";
import { ConfirmButton, ErrorAlert, KeyValue, PageHeader, PageLoader } from "@/components/common";
import { JobStatusBadge, VersionStatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/input";
import { Alert, Progress, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan, useWorkspace, useWsPath } from "@/features/workspace/context";
import { formatBytes, formatDateTime, formatDuration, formatInt, formatNumber } from "@/lib/format";
import { EditDatasetDialog } from "./EditDatasetDialog";
import { EpisodeViewer, mediaUrl } from "./EpisodeViewer";
import { ValidationReportView } from "./ValidationReportView";

function VersionOverview({ v }: { v: Schemas["DatasetVersion"] }) {
  const { t, i18n } = useTranslation();
  const features = Object.entries(v.features ?? {});
  return (
    <div className="space-y-6">
      <KeyValue
        items={[
          [t("datasets.episodes"), formatInt(v.total_episodes, i18n.language)],
          [t("datasets.frames"), formatInt(v.total_frames, i18n.language)],
          [t("datasets.fps"), formatNumber(v.fps, i18n.language)],
          [t("datasets.size"), formatBytes(v.size_bytes, i18n.language)],
          [
            t("datasets.codebase"),
            `${v.codebase_version ?? "—"}${v.converted_from ? ` (${t("datasets.converted_from", { from: v.converted_from })})` : ""}`,
          ],
          [t("datasets.robot_type"), v.robot_type ?? "—"],
          [t("datasets.state_dim"), `${v.state_dim ?? "—"}`],
          [t("datasets.action_dim"), `${v.action_dim ?? "—"}`],
          [
            t("datasets.source"),
            `${t(`datasets.source_kind.${v.source}`)}${v.source_ref ? ` · ${v.source_ref}` : ""}`,
          ],
          [
            t("datasets.content_hash"),
            <code key="h" className="break-all text-xs">
              {v.content_hash ?? "—"}
            </code>,
          ],
        ]}
      />
      <div>
        <h3 className="mb-2 font-extrabold text-base">{t("datasets.cameras")}</h3>
        <div className="flex flex-wrap gap-2">
          {v.camera_keys.map((c) => (
            <Badge key={c} variant="secondary">
              {c}
            </Badge>
          ))}
        </div>
      </div>
      <div>
        <h3 className="mb-2 font-extrabold text-base">{t("datasets.joints")}</h3>
        <div className="flex flex-wrap gap-2">
          {v.joint_names.map((j) => (
            <Badge key={j} variant="outline">
              {j}
            </Badge>
          ))}
        </div>
      </div>
      {v.tasks?.length ? (
        <div>
          <h3 className="mb-2 font-extrabold text-base">{t("datasets.tasks")}</h3>
          <ul className="list-inside list-disc text-sm">
            {v.tasks.map((task) => (
              <li key={task}>{task}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {features.length ? (
        <div>
          <h3 className="mb-2 font-extrabold text-base">{t("datasets.features")}</h3>
          <Table>
            <THead>
              <TR>
                <TH>{t("datasets.feature")}</TH>
                <TH>dtype</TH>
                <TH>shape</TH>
              </TR>
            </THead>
            <TBody>
              {features.map(([k, f]) => (
                <TR key={k}>
                  <TD>
                    <code className="break-all text-sm">{k}</code>
                  </TD>
                  <TD>{f.dtype}</TD>
                  <TD>[{f.shape.join(", ")}]</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      ) : null}
    </div>
  );
}

function EpisodesTab({ versionId }: { versionId: string }) {
  const { t, i18n } = useTranslation();
  const preview = useDatasetPreview(versionId, true);
  if (preview.isPending) return <PageLoader />;
  if (preview.isError) return <ErrorAlert error={preview.error} />;
  const p = preview.data;
  const max = Math.max(1, ...p.length_histogram.counts);
  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-2 font-extrabold text-base">{t("episode.length_distribution")}</h3>
        <div className="flex h-24 items-end gap-1" role="img" aria-label={t("episode.length_distribution")}>
          {p.length_histogram.counts.map((c, i) => (
            <div key={i} className="flex flex-1 flex-col items-center gap-1">
              <div
                className="w-full rounded-t bg-primary/70"
                style={{ height: `${(c / max) * 80}px` }}
                title={`${c}`}
              />
              <span className="text-[10px] text-muted-foreground">
                {formatDuration(p.length_histogram.bin_edges_s[i], i18n.language)}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {p.episodes.slice(0, 24).map((e) => {
          const thumb = Object.values(e.thumbnails)[0];
          return (
            <div key={e.index} className="overflow-hidden rounded border text-xs">
              {thumb ? (
                <img
                  src={mediaUrl(versionId, thumb)}
                  alt={t("episode.thumb_alt", { index: e.index })}
                  loading="lazy"
                  className="aspect-video w-full bg-muted object-cover"
                />
              ) : (
                <div className="aspect-video bg-muted" />
              )}
              <div className="flex justify-between p-1">
                <span>#{e.index}</span>
                <span>{formatDuration(e.duration_s, i18n.language)}</span>
                {e.has_issues ? <span className="text-warning">⚠</span> : null}
              </div>
            </div>
          );
        })}
      </div>
      <EpisodeViewer versionId={versionId} episodes={p.episodes} />
    </div>
  );
}

function ValidationTab({ version }: { version: Schemas["DatasetVersion"] }) {
  const { t } = useTranslation();
  const active = isVersionActive(version.status);
  const report = useValidationReport(version.id, active);
  const revalidate = useRevalidate(version.id);
  const canWrite = useCan("member");
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);
  const cancelJob = useCancelJob();
  return (
    <div className="space-y-4">
      {canWrite && !active ? (
        <Button
          variant="outline"
          onClick={() => {
            revalidate.mutate(undefined, {
              onSuccess: (j) => {
                setJobId(j.id);
              },
            });
          }}
          disabled={revalidate.isPending}
        >
          <PxIcon name="refresh" />
          {t("validation.rerun")}
        </Button>
      ) : null}
      {job.data ? (
        <div className="flex items-center gap-2 text-sm">
          <JobStatusBadge status={job.data.status} />
          <Progress
            className="max-w-xs"
            value={job.data.progress * 100}
            aria-label={t("validation.job_progress")}
          />
          {canWrite && (job.data.status === "queued" || job.data.status === "running") ? (
            <Button
              variant="ghost"
              size="sm"
              disabled={cancelJob.isPending}
              onClick={() => {
                if (jobId) cancelJob.mutate(jobId);
              }}
            >
              {t("validation.cancel_job")}
            </Button>
          ) : null}
        </div>
      ) : null}
      <ErrorAlert error={revalidate.error ?? cancelJob.error} />
      {report.isPending ? <PageLoader /> : null}
      {report.isError ? <ErrorAlert error={report.error} /> : null}
      {report.data ? <ValidationReportView report={report.data} /> : null}
    </div>
  );
}

function MergeCard({
  datasetId,
  versions,
}: {
  datasetId: string;
  versions: Schemas["DatasetVersionSummary"][];
}) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const merge = useMergeDatasets();
  const [selected, setSelected] = useState<string[]>([]);
  const ready = versions.filter((v) => v.status === "ready");
  if (ready.length < 2) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PxIcon name="merge" />
          {t("datasets.merge")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{t("datasets.merge_help")}</p>
        <div className="flex flex-wrap gap-4">
          {ready.map((v) => (
            <label key={v.id} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={selected.includes(v.id)}
                onChange={(e) => {
                  setSelected((s) => (e.target.checked ? [...s, v.id] : s.filter((x) => x !== v.id)));
                }}
              />
              v{v.version}
            </label>
          ))}
        </div>
        <ErrorAlert error={merge.error} />
        {merge.data ? (
          <Alert variant="success">
            {t("datasets.merge_started", { version: merge.data.version.version })}
          </Alert>
        ) : null}
        <Button
          disabled={selected.length < 2 || merge.isPending}
          onClick={() => {
            merge.mutate({
              workspace_id: ws.workspace_id,
              dataset_id: datasetId,
              source_version_ids: selected,
            });
          }}
        >
          {t("datasets.merge_start")}
        </Button>
      </CardContent>
    </Card>
  );
}

/** getDataset + listDatasetVersions + getDatasetVersion/validation/preview/episodes. */
export function DatasetDetailPage() {
  const { t, i18n } = useTranslation();
  const { datasetId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const path = useWsPath();
  const ws = useWorkspace();
  const canWrite = useCan("member");
  const canAdmin = useCan("admin");
  const dataset = useDataset(datasetId);
  const versions = useDatasetVersions(datasetId);
  const versionId =
    params.get("v") ?? dataset.data?.latest_version?.id ?? versions.data?.items[0]?.id ?? null;
  const version = useDatasetVersion(versionId);
  const del = useDeleteDataset(ws.workspace_id);
  const delVersion = useDeleteDatasetVersion(datasetId);
  const tab = params.get("tab") ?? "overview";

  if (dataset.isPending) return <PageLoader />;
  if (dataset.isError) return <ErrorAlert error={dataset.error} />;
  const d = dataset.data;
  const v = version.data;
  const setTab = (next: string) => {
    const p = new URLSearchParams(params);
    p.set("tab", next);
    setParams(p, { replace: true });
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader
        title={d.name}
        description={d.description || undefined}
        actions={
          <>
            {canWrite ? <EditDatasetDialog dataset={d} /> : null}
            {canWrite ? (
              <Button variant="outline" asChild>
                <Link to={path(`datasets/upload?dataset=${d.id}`)}>
                  <PxIcon name="upload" />
                  {t("datasets.new_version")}
                </Link>
              </Button>
            ) : null}
            {canWrite && v?.status === "ready" ? (
              <Button asChild>
                <Link to={path(`runs/new?version=${v.id}`)}>
                  <PxIcon name="sprout" />
                  {t("datasets.train")}
                </Link>
              </Button>
            ) : null}
            {canAdmin ? (
              <ConfirmButton
                variant="ghost"
                destructive
                title={t("datasets.delete_confirm", { name: d.name })}
                description={t("datasets.delete_help")}
                confirmLabel={t("common.delete")}
                onConfirm={async () => {
                  await del.mutateAsync(d.id);
                  navigate(path("datasets"));
                }}
                aria-label={t("common.delete")}
              >
                <PxIcon name="trash" />
              </ConfirmButton>
            ) : null}
          </>
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>{t("datasets.versions")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>{t("datasets.version")}</TH>
                <TH>{t("common.status")}</TH>
                <TH>{t("datasets.episodes")}</TH>
                <TH>{t("datasets.size")}</TH>
                <TH>{t("common.created")}</TH>
                <TH>
                  <span className="sr-only">{t("common.actions")}</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {(versions.data?.items ?? []).map((ver) => (
                <TR
                  key={ver.id}
                  aria-current={ver.id === versionId ? "true" : undefined}
                  className={ver.id === versionId ? "bg-muted" : undefined}
                >
                  <TD>
                    <Button
                      variant="link"
                      className="h-auto p-0"
                      onClick={() => {
                        setParams({ v: ver.id, tab });
                      }}
                    >
                      v{ver.version}
                    </Button>
                  </TD>
                  <TD>
                    <VersionStatusBadge status={ver.status} />
                  </TD>
                  <TD>{formatInt(ver.total_episodes, i18n.language)}</TD>
                  <TD>{formatBytes(ver.size_bytes, i18n.language)}</TD>
                  <TD>{formatDateTime(ver.created_at, i18n.language)}</TD>
                  <TD className="space-x-1 text-right">
                    {ver.status === "ready" ? (
                      <Button variant="ghost" size="sm" asChild>
                        <a
                          href={apiUrl(`/dataset-versions/${ver.id}/archive`)}
                          aria-label={t("datasets.download_version", { version: ver.version })}
                        >
                          <PxIcon name="download" />
                        </a>
                      </Button>
                    ) : null}
                    {canAdmin ? (
                      <ConfirmButton
                        variant="ghost"
                        size="sm"
                        destructive
                        title={t("datasets.delete_version_confirm", { version: ver.version })}
                        confirmLabel={t("common.delete")}
                        onConfirm={() => delVersion.mutateAsync(ver.id)}
                        aria-label={t("datasets.delete_version", { version: ver.version })}
                      >
                        <PxIcon name="trash" />
                      </ConfirmButton>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
      {canWrite ? <MergeCard datasetId={d.id} versions={versions.data?.items ?? []} /> : null}
      {version.isPending && versionId ? <PageLoader /> : null}
      <ErrorAlert error={version.error} />
      {v ? (
        <Card>
          <CardHeader className="flex-row flex-wrap items-center gap-3 space-y-0">
            <CardTitle>{t("datasets.version_title", { version: v.version })}</CardTitle>
            <VersionStatusBadge status={v.status} />
            {v.error_code ? (
              <Badge variant="destructive">
                {t(`errors.${v.error_code}`, { defaultValue: v.error_code })}
              </Badge>
            ) : null}
          </CardHeader>
          <CardContent>
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList>
                <TabsTrigger value="overview">{t("datasets.tab.overview")}</TabsTrigger>
                <TabsTrigger value="validation">{t("datasets.tab.validation")}</TabsTrigger>
                <TabsTrigger value="episodes" disabled={v.status !== "ready"}>
                  {t("datasets.tab.episodes")}
                </TabsTrigger>
              </TabsList>
              <TabsContent value="overview">
                <VersionOverview v={v} />
              </TabsContent>
              <TabsContent value="validation">
                <ValidationTab version={v} />
              </TabsContent>
              <TabsContent value="episodes">
                {v.status === "ready" ? <EpisodesTab versionId={v.id} /> : null}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
