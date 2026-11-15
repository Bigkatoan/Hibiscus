import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";
import { api, newIdempotencyKey, unwrap, type Schemas } from "../client";
import { qk } from "./keys";

type S = Schemas;

export const TERMINAL_RUN_STATUSES: readonly S["RunStatus"][] = ["succeeded", "failed", "cancelled"];
export const ACTIVE_RUN_STATUSES: readonly S["RunStatus"][] = [
  "queued",
  "preparing",
  "running",
  "pausing",
  "exporting",
  "cancelling",
];

export function isRunTerminal(status: S["RunStatus"]): boolean {
  return TERMINAL_RUN_STATUSES.includes(status);
}

export function usePolicies() {
  return useQuery({
    queryKey: qk.policies,
    queryFn: () => unwrap(api.GET("/policies")),
    staleTime: 10 * 60_000,
  });
}

export function usePolicy(type: S["PolicyType"] | null) {
  return useQuery({
    queryKey: qk.policy(type ?? ""),
    queryFn: () =>
      unwrap(api.GET("/policies/{policy_type}", { params: { path: { policy_type: type ?? "act" } } })),
    enabled: type !== null,
    staleTime: 10 * 60_000,
  });
}

export interface RunFilters {
  status?: S["RunStatus"][];
  policy_type?: S["PolicyType"];
  dataset_id?: string;
  created_by?: string;
  q?: string;
}

export function useRuns(ws: string, filters: RunFilters = {}) {
  return useInfiniteQuery({
    queryKey: [...qk.runs(ws), filters],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/runs", {
          params: {
            query: {
              workspace_id: ws,
              limit: 50,
              ...(filters.status?.length ? { status: filters.status } : {}),
              ...(filters.policy_type ? { policy_type: filters.policy_type } : {}),
              ...(filters.dataset_id ? { dataset_id: filters.dataset_id } : {}),
              ...(filters.created_by ? { created_by: filters.created_by } : {}),
              ...(filters.q ? { q: filters.q } : {}),
              ...(pageParam ? { cursor: pageParam } : {}),
            },
          },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    placeholderData: keepPreviousData,
    refetchInterval: (query) => {
      const items = query.state.data?.pages.flatMap((p) => p.items) ?? [];
      return items.some((r) => !isRunTerminal(r.status) && r.status !== "paused") ? 10_000 : false;
    },
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: qk.run(id),
    queryFn: () => unwrap(api.GET("/runs/{run_id}", { params: { path: { run_id: id } } })),
    enabled: !!id,
  });
}

export function usePreflight() {
  return useMutation({
    mutationFn: (body: S["RunCreate"]) => unwrap(api.POST("/runs/preflight", { body })),
  });
}

export function useCreateRun() {
  const qc = useQueryClient();
  // One key per wizard instance: a double-click / retry replays instead of creating twice.
  const [key] = useState(newIdempotencyKey);
  return useMutation({
    mutationFn: (body: S["RunCreate"]) =>
      unwrap(api.POST("/runs", { body, params: { header: { "Idempotency-Key": key } } })),
    onSuccess: (run) => qc.invalidateQueries({ queryKey: qk.runs(run.workspace_id) }),
  });
}

function useRunAction<TVars>(fn: (vars: TVars) => Promise<S["Run"]>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (run) => {
      qc.setQueryData(qk.run(run.id), run);
      await qc.invalidateQueries({ queryKey: qk.runs(run.workspace_id) });
    },
  });
}

export function useCancelRun() {
  return useRunAction((id: string) =>
    unwrap(api.POST("/runs/{run_id}/cancel", { params: { path: { run_id: id } } })),
  );
}

export function usePauseRun() {
  return useRunAction(({ id, mode }: { id: string; mode: "next_checkpoint" | "now" }) =>
    unwrap(api.POST("/runs/{run_id}/pause", { params: { path: { run_id: id } }, body: { mode } })),
  );
}

export function useResumeRun() {
  return useRunAction(({ id, body }: { id: string; body: S["RunResumeRequest"] }) =>
    unwrap(api.POST("/runs/{run_id}/resume", { params: { path: { run_id: id } }, body })),
  );
}

export function useUpdateRun() {
  return useRunAction(({ id, body }: { id: string; body: S["RunUpdate"] }) =>
    unwrap(api.PATCH("/runs/{run_id}", { params: { path: { run_id: id } }, body })),
  );
}

export function useCloneRun() {
  return useRunAction(({ id, body }: { id: string; body: S["RunCloneRequest"] }) =>
    unwrap(api.POST("/runs/{run_id}/clone", { params: { path: { run_id: id } }, body })),
  );
}

export function useRunMetrics(id: string, keys?: string[]) {
  return useQuery({
    queryKey: [...qk.runMetrics(id), keys ?? []],
    queryFn: () =>
      unwrap(
        api.GET("/runs/{run_id}/metrics", {
          params: { path: { run_id: id }, query: { max_points: 2000, ...(keys?.length ? { keys } : {}) } },
        }),
      ),
    staleTime: Infinity,
  });
}

export function useRunTelemetry(id: string) {
  return useQuery({
    queryKey: qk.runTelemetry(id),
    queryFn: () =>
      unwrap(
        api.GET("/runs/{run_id}/telemetry", {
          params: { path: { run_id: id }, query: { max_points: 1000 } },
        }),
      ),
    staleTime: Infinity,
  });
}

export function useRunEventsHistory(id: string, types?: S["RunEventType"][]) {
  return useQuery({
    queryKey: [...qk.runEvents(id), types ?? []],
    queryFn: () =>
      unwrap(
        api.GET("/runs/{run_id}/events/history", {
          params: { path: { run_id: id }, query: { limit: 1000, ...(types ? { types } : {}) } },
        }),
      ),
    staleTime: Infinity,
  });
}

export function useCheckpoints(id: string) {
  return useQuery({
    queryKey: qk.runCheckpoints(id),
    queryFn: () => unwrap(api.GET("/runs/{run_id}/checkpoints", { params: { path: { run_id: id } } })),
  });
}

export function useRunManifest(id: string, enabled: boolean) {
  return useQuery({
    queryKey: qk.runManifest(id),
    queryFn: () => unwrap(api.GET("/runs/{run_id}/manifest", { params: { path: { run_id: id } } })),
    enabled,
    retry: false,
  });
}

export function useExportCheckpoint(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ step, options }: { step: number; options: S["ExportOptions"] }) =>
      unwrap(
        api.POST("/runs/{run_id}/checkpoints/{step}/export", {
          params: { path: { run_id: runId, step } },
          body: options,
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.runCheckpoints(runId) }),
  });
}

export function useEvalCheckpoint(runId: string) {
  return useMutation({
    mutationFn: (step: number) =>
      unwrap(
        api.POST("/runs/{run_id}/checkpoints/{step}/eval", { params: { path: { run_id: runId, step } } }),
      ),
  });
}

export function useCheckpointEval(runId: string, step: number | null) {
  return useQuery({
    queryKey: qk.runEval(runId, step ?? -1),
    queryFn: () =>
      unwrap(
        api.GET("/runs/{run_id}/checkpoints/{step}/eval-result", {
          params: { path: { run_id: runId, step: step ?? 1 } },
        }),
      ),
    enabled: step !== null,
    retry: false,
  });
}

export function useLogSearch(runId: string, q: string) {
  return useQuery({
    queryKey: qk.logSearch(runId, q),
    queryFn: () =>
      unwrap(
        api.GET("/runs/{run_id}/logs/search", {
          params: { path: { run_id: runId }, query: { q, limit: 200 } },
        }),
      ),
    enabled: q.length >= 2,
  });
}

export function useCompareRuns(ids: string[], keys: string[]) {
  return useQuery({
    queryKey: qk.compare(ids, keys),
    queryFn: () => unwrap(api.GET("/runs/compare", { params: { query: { ids, keys, max_points: 1000 } } })),
    enabled: ids.length >= 2 && ids.length <= 8,
  });
}
