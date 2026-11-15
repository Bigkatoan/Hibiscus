import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect } from "react";
import { useRuntime } from "../ws/StationProvider";
import { api } from "./client";
import type {
  CalibrationFile,
  CompatReport,
  DiscoveredCamera,
  Job,
  LocalDataset,
  LocalDatasetDetail,
  ModelEntry,
  Port,
  RobotProfile,
  ServerDataset,
  ServerLink,
  ServerModel,
  ServerRun,
  Session,
  SessionSummary,
  Settings,
  Status,
  TelemetrySeries,
} from "./types";

export const qk = {
  status: ["station", "status"],
  settings: ["station", "settings"],
  robots: ["station", "robots"],
  ports: ["station", "ports"],
  calibrations: ["station", "calibrations"],
  discover: ["station", "cameras", "discover"],
  datasets: ["station", "datasets"],
  dataset: (name: string) => ["station", "datasets", name],
  episodeTelemetry: (name: string, i: number) => ["station", "datasets", name, "episodes", i],
  models: ["station", "models"],
  compat: (key: string, robot: string) => ["station", "models", key, "compat", robot],
  jobs: ["station", "jobs"],
  sessions: ["station", "sessions"],
  sessionTelemetry: (id: string) => ["station", "sessions", id, "telemetry"],
  server: ["station", "server"],
  serverDatasets: ["station", "server", "datasets"],
  serverModels: ["station", "server", "models"],
  serverRuns: (datasetId: string) => ["station", "server", "runs", datasetId],
} as const;

/** GET /status, mirrored into the live store (the WS keeps it fresh afterwards). */
export function useStatusQuery() {
  const { store } = useRuntime();
  const q = useQuery({ queryKey: qk.status, queryFn: () => api.get<Status>("/status") });
  useEffect(() => {
    if (q.data) store.setStatus(q.data);
  }, [q.data, store]);
  return q;
}

export const useSettings = () =>
  useQuery({ queryKey: qk.settings, queryFn: () => api.get<Settings>("/settings") });

export const useRobots = () =>
  useQuery({
    queryKey: qk.robots,
    queryFn: () => api.get<{ robots: RobotProfile[]; active: string | null }>("/robots"),
  });

export const usePorts = () =>
  useQuery({ queryKey: qk.ports, queryFn: () => api.get<{ ports: Port[] }>("/ports") });

export const useCalibrations = () =>
  useQuery({
    queryKey: qk.calibrations,
    queryFn: () => api.get<{ files: CalibrationFile[] }>("/calibrations"),
  });

export const useDiscoverCameras = (enabled = true) =>
  useQuery({
    queryKey: qk.discover,
    queryFn: () => api.get<{ cameras: DiscoveredCamera[] }>("/cameras/discover"),
    enabled,
  });

export const useDatasets = () =>
  useQuery({ queryKey: qk.datasets, queryFn: () => api.get<{ datasets: LocalDataset[] }>("/datasets") });

export const useDataset = (name: string) =>
  useQuery({
    queryKey: qk.dataset(name),
    queryFn: () => api.get<LocalDatasetDetail>(`/datasets/${encodeURIComponent(name)}`),
  });

export const useEpisodeTelemetry = (name: string, index: number | null) =>
  useQuery({
    queryKey: qk.episodeTelemetry(name, index ?? -1),
    queryFn: () =>
      api.get<TelemetrySeries>(`/datasets/${encodeURIComponent(name)}/episodes/${String(index)}/telemetry`),
    enabled: index !== null,
  });

export const useModels = () =>
  useQuery({
    queryKey: qk.models,
    queryFn: () => api.get<{ models: ModelEntry[]; loaded: string | null }>("/models"),
  });

export const useCompat = (key: string | null, robot: string | null) =>
  useQuery({
    queryKey: qk.compat(key ?? "", robot ?? ""),
    queryFn: () =>
      api.get<CompatReport>(`/models/${encodeURIComponent(key ?? "")}/compat`, {
        query: { robot: robot ?? undefined },
      }),
    enabled: key !== null,
  });

export const useJobs = () => {
  const { store } = useRuntime();
  const q = useQuery({ queryKey: qk.jobs, queryFn: () => api.get<{ jobs: Job[] }>("/jobs") });
  useEffect(() => {
    for (const j of q.data?.jobs ?? []) store.setJob(j);
  }, [q.data, store]);
  return q;
};

export const useSessions = () =>
  useQuery({
    queryKey: qk.sessions,
    queryFn: () => api.get<{ sessions: SessionSummary[] }>("/sessions"),
  });

export const useServer = () =>
  useQuery({ queryKey: qk.server, queryFn: () => api.get<ServerLink>("/server") });

export const useServerDatasets = (enabled: boolean) =>
  useQuery({
    queryKey: qk.serverDatasets,
    queryFn: () => api.get<{ datasets: ServerDataset[] }>("/server/datasets"),
    enabled,
  });

export const useServerModels = (enabled: boolean) =>
  useQuery({
    queryKey: qk.serverModels,
    queryFn: () => api.get<{ models: ServerModel[] }>("/server/models"),
    enabled,
  });

export const useServerRuns = (datasetId: string | null) =>
  useQuery({
    queryKey: qk.serverRuns(datasetId ?? ""),
    queryFn: () => api.get<{ runs: ServerRun[] }>("/server/runs", { query: { dataset_id: datasetId ?? "" } }),
    enabled: datasetId !== null,
  });

function isStatus(v: unknown): v is Status {
  return typeof v === "object" && v !== null && "state" in v && "station" in v;
}

function isJob(v: unknown): v is Job {
  return typeof v === "object" && v !== null && "kind" in v && "status" in v && "progress" in v;
}

/**
 * Mutation that mirrors Status / Job responses into the live store and invalidates queries.
 * Hardware commands answer once the owner accepted the transition (§5.1), so the returned
 * Status is already the new state.
 */
export function useStationMutation<TVars, TRes>(
  fn: (vars: TVars) => Promise<TRes>,
  invalidate: QueryKey[] = [],
) {
  const qc = useQueryClient();
  const { store } = useRuntime();
  return useMutation({
    mutationFn: fn,
    onSuccess: (res) => {
      if (isStatus(res)) {
        store.setStatus(res);
        qc.setQueryData(qk.status, res);
      } else if (isJob(res)) store.setJob(res);
      else if (res && typeof res === "object" && "kind" in res && "controls" in res) {
        const st = store.getSnapshot().status;
        if (st) store.setStatus({ ...st, session: res as unknown as Session });
      }
      for (const key of invalidate) void qc.invalidateQueries({ queryKey: key });
    },
  });
}
