import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "../client";
import { qk } from "./keys";

type S = Schemas;

const ACTIVE_VERSION: readonly S["DatasetVersionStatus"][] = ["pending", "unpacking", "validating"];

export function isVersionActive(status: S["DatasetVersionStatus"] | undefined): boolean {
  return status !== undefined && ACTIVE_VERSION.includes(status);
}

export function useDatasets(ws: string, q: string) {
  return useInfiniteQuery({
    queryKey: [...qk.datasets(ws), q],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/datasets", {
          params: {
            query: {
              workspace_id: ws,
              limit: 50,
              ...(q ? { q } : {}),
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
      return items.some((d) => isVersionActive(d.latest_version?.status)) ? 5000 : false;
    },
  });
}

export function useDataset(id: string) {
  return useQuery({
    queryKey: qk.dataset(id),
    queryFn: () => unwrap(api.GET("/datasets/{dataset_id}", { params: { path: { dataset_id: id } } })),
  });
}

export function useCreateDataset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["DatasetCreate"]) => unwrap(api.POST("/datasets", { body })),
    onSuccess: (d) => qc.invalidateQueries({ queryKey: qk.datasets(d.workspace_id) }),
  });
}

export function useUpdateDataset(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["DatasetUpdate"]) =>
      unwrap(api.PATCH("/datasets/{dataset_id}", { params: { path: { dataset_id: id } }, body })),
    onSuccess: (d) => {
      qc.setQueryData(qk.dataset(id), d);
      return qc.invalidateQueries({ queryKey: qk.datasets(d.workspace_id) });
    },
  });
}

export function useDeleteDataset(ws: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/datasets/{dataset_id}", { params: { path: { dataset_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.datasets(ws) }),
  });
}

export function useDatasetVersions(datasetId: string) {
  return useQuery({
    queryKey: qk.datasetVersions(datasetId),
    queryFn: () =>
      unwrap(
        api.GET("/datasets/{dataset_id}/versions", {
          params: { path: { dataset_id: datasetId }, query: { limit: 200 } },
        }),
      ),
    enabled: !!datasetId,
    refetchInterval: (q) => (q.state.data?.items.some((v) => isVersionActive(v.status)) ? 4000 : false),
  });
}

export function useDatasetVersion(versionId: string | null | undefined) {
  return useQuery({
    queryKey: qk.datasetVersion(versionId ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/dataset-versions/{version_id}", { params: { path: { version_id: versionId ?? "" } } }),
      ),
    enabled: !!versionId,
    refetchInterval: (q) => (isVersionActive(q.state.data?.status) ? 4000 : false),
  });
}

export function useDeleteDatasetVersion(datasetId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (versionId: string) =>
      unwrap(api.DELETE("/dataset-versions/{version_id}", { params: { path: { version_id: versionId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.datasetVersions(datasetId) }),
  });
}

export function useValidationReport(versionId: string, poll: boolean) {
  return useQuery({
    queryKey: qk.validation(versionId),
    queryFn: () =>
      unwrap(
        api.GET("/dataset-versions/{version_id}/validation", { params: { path: { version_id: versionId } } }),
      ),
    refetchInterval: (q) => (poll || q.state.data?.summary.result === "running" ? 3000 : false),
  });
}

export function useRevalidate(versionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/dataset-versions/{version_id}/validation", {
          params: { path: { version_id: versionId } },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.validation(versionId) });
      await qc.invalidateQueries({ queryKey: qk.datasetVersion(versionId) });
    },
  });
}

export function useDatasetPreview(versionId: string, enabled: boolean) {
  return useQuery({
    queryKey: qk.preview(versionId),
    queryFn: () =>
      unwrap(
        api.GET("/dataset-versions/{version_id}/preview", { params: { path: { version_id: versionId } } }),
      ),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useEpisode(versionId: string, episodeIndex: number | null) {
  return useQuery({
    queryKey: qk.episode(versionId, episodeIndex ?? -1),
    queryFn: () =>
      unwrap(
        api.GET("/dataset-versions/{version_id}/episodes/{episode_index}", {
          params: {
            path: { version_id: versionId, episode_index: episodeIndex ?? 0 },
            query: { max_points: 1000 },
          },
        }),
      ),
    enabled: episodeIndex !== null,
    staleTime: 5 * 60_000,
  });
}

export function useImportHf() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["HfImportRequest"]) => unwrap(api.POST("/datasets/import-hf", { body })),
    onSuccess: (r) => qc.invalidateQueries({ queryKey: qk.datasets(r.dataset.workspace_id) }),
  });
}

export function useMergeDatasets() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["MergeRequest"]) => unwrap(api.POST("/datasets/merge", { body })),
    onSuccess: (r) => qc.invalidateQueries({ queryKey: qk.datasets(r.dataset.workspace_id) }),
  });
}

export function useActiveUploads(ws: string) {
  return useQuery({
    queryKey: qk.uploads(ws),
    queryFn: () =>
      unwrap(api.GET("/uploads", { params: { query: { workspace_id: ws, status: "active", limit: 50 } } })),
  });
}
