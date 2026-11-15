import { PxIcon } from "@/hibiscus/PixelAnim";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiUrl, authFetch } from "@/api/client";
import { useLogSearch } from "@/api/hooks/runs";
import { ErrorAlert } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Checkbox, Input } from "@/components/ui/input";

const EARLIER_CHUNK = 64 * 1024;

/** Range request for log bytes [start, end] (getRunLogs, `Range: bytes=a-b`). */
export async function fetchLogRange(runId: string, start: number, end: number): Promise<string> {
  const res = await authFetch(
    new Request(apiUrl(`/runs/${runId}/logs`), {
      headers: { Range: `bytes=${start}-${end}` },
      credentials: "same-origin",
    }),
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

/** Live log tail (SSE `log` events), earlier chunks via Range, server-side search, download. */
export function LogViewer({
  runId,
  lines,
  firstOffset,
  terminal = false,
}: {
  runId: string;
  lines: string[];
  firstOffset: number | null;
  /** Finished run: no live tail will come, so the stored log is loaded right away (QC-e2e-11). */
  terminal?: boolean;
}) {
  const { t } = useTranslation();
  const [follow, setFollow] = useState(true);
  const [earlier, setEarlier] = useState<string[]>([]);
  const [earliestOffset, setEarliestOffset] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const search = useLogSearch(runId, submitted);
  const box = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines, follow]);

  const offset = earliestOffset ?? firstOffset;
  const loadEarlier = async () => {
    if (offset === null || offset <= 0) return;
    const start = Math.max(0, offset - EARLIER_CHUNK);
    try {
      const text = await fetchLogRange(runId, start, offset - 1);
      const chunk = text.split("\n");
      if (start > 0) chunk.shift(); // drop the partial first line
      setEarlier((prev) => [...chunk.filter((l, i) => l !== "" || i < chunk.length - 1), ...prev]);
      setEarliestOffset(start);
    } catch (e) {
      setLoadError(e);
    }
  };

  const loadFull = async () => {
    try {
      const res = await authFetch(new Request(apiUrl(`/runs/${runId}/logs`), { credentials: "same-origin" }));
      if (res.status === 404) {
        // Nothing stored (e.g. cancelled while queued): show the empty state, not an error.
        setEarliestOffset(0);
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      setEarlier(text.replace(/\n$/, "").split("\n").slice(-5000));
      setEarliestOffset(0);
    } catch (e) {
      setLoadError(e);
    }
  };

  const [autoLoaded, setAutoLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!terminal || autoLoaded || lines.length > 0) return;
    setAutoLoaded(true);
    setLoading(true);
    void loadFull().finally(() => {
      setLoading(false);
    });
    // loadFull is recreated each render; run once per mounted finished run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terminal, autoLoaded, lines.length]);

  const all = [...earlier, ...lines];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <form
          role="search"
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setSubmitted(query.trim());
          }}
        >
          <label htmlFor="log-search" className="sr-only">
            {t("logs.search")}
          </label>
          <Input
            id="log-search"
            type="search"
            className="w-56"
            placeholder={t("logs.search")}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
            }}
          />
          <Button type="submit" variant="outline" size="icon" aria-label={t("logs.search")}>
            <PxIcon name="search" />
          </Button>
        </form>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={follow}
            onChange={(e) => {
              setFollow(e.target.checked);
            }}
          />
          {t("logs.follow")}
        </label>
        {offset !== null && offset > 0 ? (
          <Button variant="outline" size="sm" onClick={() => void loadEarlier()}>
            {t("logs.load_earlier")}
          </Button>
        ) : null}
        {offset === null && all.length === 0 ? (
          <Button variant="outline" size="sm" onClick={() => void loadFull()}>
            {t("logs.load_full")}
          </Button>
        ) : null}
        <Button variant="outline" size="sm" asChild className="ml-auto">
          <a href={apiUrl(`/runs/${runId}/logs`, { download: true })}>
            <PxIcon name="download" />
            {t("logs.download")}
          </a>
        </Button>
      </div>
      <ErrorAlert error={loadError} />
      {submitted.length >= 2 ? (
        <div className="rounded-md border p-2">
          <p className="mb-2 text-sm font-medium">
            {t("logs.results", { count: search.data?.items.length ?? 0, q: submitted })}
          </p>
          <ErrorAlert error={search.error} />
          <ul className="max-h-60 overflow-auto font-mono text-xs">
            {search.data?.items.map((it) => (
              <li
                key={`${it.attempt}-${it.line_no}`}
                className="whitespace-pre-wrap break-all border-b py-0.5"
              >
                <span className="mr-2 text-muted-foreground">{it.line_no}</span>
                {it.text}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {/* Scrollable region must be keyboard-focusable (WCAG 2.1.1, axe scrollable-region-focusable). */}
      <pre
        ref={box}
        role="region"
        tabIndex={0}
        aria-label={t("logs.title")}
        aria-live="off"
        className="h-[28rem] overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted/40 p-3 font-mono text-xs leading-relaxed"
        onScroll={(e) => {
          const el = e.currentTarget;
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
          if (!atBottom && follow) setFollow(false);
        }}
      >
        {all.length ? all.join("\n") : loading ? t("logs.loading") : t("logs.empty")}
      </pre>
    </div>
  );
}
