import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { apiUrl } from "@/api/client";
import { qk } from "@/api/hooks/keys";
import { openSse, type EventSourceFactory, type SseMessage } from "@/api/sse";
import { isRecord } from "@/lib/utils";

const WS_EVENTS = [
  "heartbeat",
  "run.status",
  "dataset_version.status",
  "model.status",
  "job.status",
  "notification",
  "estimate.ready",
] as const;

/** Translate a workspace stream event (streamWorkspaceEvents) into cache invalidations. */
export function applyWorkspaceEvent(qc: QueryClient, ws: string, msg: SseMessage): void {
  const data = isRecord(msg.data) ? msg.data : {};
  const id = typeof data.id === "string" ? data.id : null;
  switch (msg.event) {
    case "run.status": {
      const runId = typeof data.run_id === "string" ? data.run_id : null;
      if (runId) void qc.invalidateQueries({ queryKey: qk.run(runId) });
      void qc.invalidateQueries({ queryKey: qk.runs(ws) });
      void qc.invalidateQueries({ queryKey: qk.gpus });
      void qc.invalidateQueries({ queryKey: qk.queue });
      break;
    }
    case "dataset_version.status":
      if (id) {
        void qc.invalidateQueries({ queryKey: qk.datasetVersion(id) });
        void qc.invalidateQueries({ queryKey: qk.validation(id) });
      }
      void qc.invalidateQueries({ queryKey: qk.datasets(ws) });
      void qc.invalidateQueries({ queryKey: ["dataset-versions"] });
      break;
    case "model.status":
      if (id) void qc.invalidateQueries({ queryKey: qk.model(id) });
      void qc.invalidateQueries({ queryKey: qk.models(ws) });
      break;
    case "job.status":
      if (id) void qc.invalidateQueries({ queryKey: qk.job(id) });
      break;
    case "notification":
      void qc.invalidateQueries({ queryKey: qk.notifications });
      break;
    default:
      break;
  }
}

export function useWorkspaceEvents(workspaceId: string | null, factory?: EventSourceFactory): void {
  const qc = useQueryClient();
  useEffect(() => {
    if (!workspaceId || typeof EventSource === "undefined") return undefined;
    const sub = openSse({
      url: () => apiUrl(`/workspaces/${workspaceId}/events`),
      events: WS_EVENTS,
      onMessage: (msg) => {
        applyWorkspaceEvent(qc, workspaceId, msg);
      },
      ...(factory ? { factory } : {}),
    });
    return () => {
      sub.close();
    };
  }, [workspaceId, qc, factory]);
}
