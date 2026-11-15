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

export interface ModelFilters {
  policy_type?: S["PolicyType"];
  verified?: boolean;
  q?: string;
  run_id?: string;
}

export function useModels(ws: string, filters: ModelFilters = {}) {
  return useInfiniteQuery({
    queryKey: [...qk.models(ws), filters],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/models", {
          params: {
            query: {
              workspace_id: ws,
              limit: 50,
              ...(filters.policy_type ? { policy_type: filters.policy_type } : {}),
              ...(filters.verified !== undefined ? { verified: filters.verified } : {}),
              ...(filters.q ? { q: filters.q } : {}),
              ...(filters.run_id ? { run_id: filters.run_id } : {}),
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
      return items.some((m) => m.status === "pending" || m.status === "building") ? 8000 : false;
    },
  });
}

export function useModel(id: string) {
  return useQuery({
    queryKey: qk.model(id),
    queryFn: () => unwrap(api.GET("/models/{model_id}", { params: { path: { model_id: id } } })),
    enabled: !!id,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "pending" || s === "building" ? 5000 : false;
    },
  });
}

export function useModelFiles(id: string, enabled: boolean) {
  return useQuery({
    queryKey: qk.modelFiles(id),
    queryFn: () => unwrap(api.GET("/models/{model_id}/files", { params: { path: { model_id: id } } })),
    enabled,
  });
}

export function useRenameModel(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(api.PATCH("/models/{model_id}", { params: { path: { model_id: id } }, body: { name } })),
    onSuccess: (m) => {
      qc.setQueryData(qk.model(id), m);
      return qc.invalidateQueries({ queryKey: qk.models(m.workspace_id) });
    },
  });
}

export function useDeleteModel(ws: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/models/{model_id}", { params: { path: { model_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.models(ws) }),
  });
}

export function usePushModelToHub(id: string) {
  return useMutation({
    mutationFn: (body: S["HubPushRequest"]) =>
      unwrap(api.POST("/models/{model_id}/push-hub", { params: { path: { model_id: id } }, body })),
  });
}

export function useReverifyModel(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/models/{model_id}/verify", { params: { path: { model_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.model(id) }),
  });
}
