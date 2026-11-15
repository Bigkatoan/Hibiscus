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

export function useAdminUsers(q: string) {
  return useInfiniteQuery({
    queryKey: qk.adminUsers(q),
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/admin/users", {
          params: { query: { limit: 50, ...(q ? { q } : {}), ...(pageParam ? { cursor: pageParam } : {}) } },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    placeholderData: keepPreviousData,
  });
}

export function useAdminUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: S["AdminUserUpdate"] }) =>
      unwrap(api.PATCH("/admin/users/{user_id}", { params: { path: { user_id: id } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function useAdminRevokeSessions() {
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/admin/users/{user_id}/revoke-sessions", { params: { path: { user_id: id } } })),
  });
}

export function useAdminResetLink() {
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/admin/users/{user_id}/password-reset-link", { params: { path: { user_id: id } } })),
  });
}

export interface AuditFilters {
  workspace_id?: string;
  actor_user_id?: string;
  action?: S["AuditAction"];
  since?: string;
  until?: string;
}

export function useAuditEvents(filters: AuditFilters) {
  return useInfiniteQuery({
    queryKey: qk.audit({ ...filters }),
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/admin/audit-events", {
          params: {
            query: {
              limit: 100,
              ...(filters.workspace_id ? { workspace_id: filters.workspace_id } : {}),
              ...(filters.actor_user_id ? { actor_user_id: filters.actor_user_id } : {}),
              ...(filters.action ? { action: filters.action } : {}),
              ...(filters.since ? { since: filters.since } : {}),
              ...(filters.until ? { until: filters.until } : {}),
              ...(pageParam ? { cursor: pageParam } : {}),
            },
          },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    placeholderData: keepPreviousData,
  });
}

export function useQuotas(ws: string) {
  return useQuery({
    queryKey: qk.quotas(ws),
    queryFn: () =>
      unwrap(api.GET("/admin/workspaces/{workspace_id}/quotas", { params: { path: { workspace_id: ws } } })),
    enabled: !!ws,
  });
}

export function useUpsertQuota(ws: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["QuotaUpsert"]) =>
      unwrap(
        api.PUT("/admin/workspaces/{workspace_id}/quotas", { params: { path: { workspace_id: ws } }, body }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.quotas(ws) }),
  });
}

export function useAdminUpdateGpu() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: "online" | "draining" | "disabled" }) =>
      unwrap(api.PATCH("/admin/gpus/{gpu_id}", { params: { path: { gpu_id: id } }, body: { status } })),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.gpus });
      await qc.invalidateQueries({ queryKey: qk.system });
    },
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: qk.system,
    queryFn: () => unwrap(api.GET("/admin/system")),
    refetchInterval: 15_000,
  });
}
