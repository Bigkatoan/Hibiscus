import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { refreshSession, apiUrl, type Schemas } from "@/api/client";
import { useEpisode } from "@/api/hooks/datasets";
import { ErrorAlert, PageLoader } from "@/components/common";
import { LineChart } from "@/components/charts/LineChart";
import type { XYSeries } from "@/components/charts/series";
import { Alert } from "@/components/ui/misc";
import { NativeSelect } from "@/components/ui/input";
import { formatDuration } from "@/lib/format";

export function mediaUrl(versionId: string, mediaPath: string): string {
  const safe = mediaPath.split("/").map(encodeURIComponent).join("/");
  return apiUrl(`/dataset-versions/${versionId}/media/${safe}`);
}

/** Group EpisodeDetail.series by feature into chart series on the shared timestamp axis. */
export function episodeChartSeries(ep: Schemas["EpisodeDetail"]): Map<string, XYSeries[]> {
  const byFeature = new Map<string, XYSeries[]>();
  for (const s of ep.series) {
    const list = byFeature.get(s.feature) ?? [];
    list.push({ label: s.name || `${s.feature}[${s.dim}]`, x: ep.timestamps, y: s.values });
    byFeature.set(s.feature, list);
  }
  return byFeature;
}

function EpisodeVideo({
  versionId,
  video,
  onTime,
  videoRef,
}: {
  versionId: string;
  video: Schemas["EpisodeDetail"]["videos"][number];
  onTime: (t: number) => void;
  videoRef: React.RefObject<HTMLVideoElement>;
}) {
  const { t } = useTranslation();
  const retried = useRef(false);
  const [failed, setFailed] = useState(false);
  const path = video.preview_media_path;
  if (!path) {
    return (
      <Alert variant="warning">
        {video.browser_playable_hint === false
          ? t("episode.no_preview_codec", { codec: video.codec })
          : t("episode.preview_pending")}
      </Alert>
    );
  }
  return (
    <figure className="space-y-1">
      <video
        ref={videoRef}
        className="aspect-video w-full rounded bg-black"
        src={mediaUrl(versionId, path)}
        poster={video.thumbnail_media_path ? mediaUrl(versionId, video.thumbnail_media_path) : undefined}
        controls
        preload="metadata"
        playsInline
        muted
        onTimeUpdate={(e) => {
          onTime(e.currentTarget.currentTime);
        }}
        onError={(e) => {
          // The access cookie may have expired (15 min): refresh once and reload the source.
          const el = e.currentTarget;
          if (retried.current) {
            setFailed(true);
            return;
          }
          retried.current = true;
          void refreshSession().then((ok) => {
            if (ok) {
              el.load();
            } else setFailed(true);
          });
        }}
      >
        <track kind="captions" />
      </video>
      <figcaption className="text-xs text-muted-foreground">
        {video.camera_key} ·{" "}
        {t("episode.preview_caption", { w: video.width, h: video.height, codec: video.codec })}
      </figcaption>
      {failed ? <Alert variant="destructive">{t("episode.video_error")}</Alert> : null}
    </figure>
  );
}

/** Episode viewer: H.264 preview player + joint time-series (getEpisode, getDatasetMedia). */
export function EpisodeViewer({
  versionId,
  episodes,
}: {
  versionId: string;
  episodes: Schemas["EpisodeSummary"][];
}) {
  const { t, i18n } = useTranslation();
  const [index, setIndex] = useState<number>(episodes[0]?.index ?? 0);
  const [camera, setCamera] = useState(0);
  const [time, setTime] = useState<number | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const ep = useEpisode(versionId, episodes.length ? index : null);
  const groups = useMemo(
    () => (ep.data ? episodeChartSeries(ep.data) : new Map<string, XYSeries[]>()),
    [ep.data],
  );
  const video = ep.data?.videos[camera] ?? ep.data?.videos[0];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-sm">
          <span className="block font-medium">{t("episode.select")}</span>
          <NativeSelect
            className="w-56"
            value={index}
            onChange={(e) => {
              setIndex(Number(e.target.value));
              setTime(null);
            }}
          >
            {episodes.map((e) => (
              <option key={e.index} value={e.index}>
                {t("episode.option", {
                  index: e.index,
                  duration: formatDuration(e.duration_s, i18n.language),
                })}
                {e.has_issues ? " ⚠" : ""}
              </option>
            ))}
          </NativeSelect>
        </label>
        {(ep.data?.videos.length ?? 0) > 1 ? (
          <label className="space-y-1 text-sm">
            <span className="block font-medium">{t("episode.camera")}</span>
            <NativeSelect
              className="w-64"
              value={camera}
              onChange={(e) => {
                setCamera(Number(e.target.value));
              }}
            >
              {ep.data?.videos.map((v, i) => (
                <option key={v.camera_key} value={i}>
                  {v.camera_key}
                </option>
              ))}
            </NativeSelect>
          </label>
        ) : null}
      </div>
      {ep.isPending ? <PageLoader /> : null}
      <ErrorAlert error={ep.error} />
      {ep.data ? (
        <div className="grid gap-6 xl:grid-cols-2">
          <div>
            {video ? (
              <EpisodeVideo
                key={`${index}-${video.camera_key}`}
                versionId={versionId}
                video={video}
                onTime={setTime}
                videoRef={videoRef}
              />
            ) : null}
          </div>
          <div className="space-y-6">
            {[...groups.entries()].map(([feature, series]) => (
              <LineChart
                key={feature}
                title={t("episode.chart_title", { feature })}
                series={series}
                xLabel={t("episode.time_s")}
                syncKey={`ep-${versionId}`}
                markerX={time}
                height={200}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
