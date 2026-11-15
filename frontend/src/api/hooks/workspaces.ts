import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "../client";
import { qk } from "./keys";

type S = Schemas;

export function useWorkspaces(enabled = true) {
  return useQuery({
    queryKey: qk.workspaces,
    queryFn: () => unwrap(api.GET("/workspaces")),
    enabled,
  });
}

export function useCreateWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["WorkspaceCreate"]) => unwrap(api.POST("/workspaces", { body })),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.workspaces });
      await qc.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useWorkspaceDetail(id: string) {
  return useQuery({
    queryKey: qk.workspace(id),
    queryFn: () => unwrap(api.GET("/workspaces/{workspace_id}", { params: { path: { workspace_id: id } } })),
  });
}

export function useUpdateWorkspace(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["WorkspaceUpdate"]) =>
      unwrap(api.PATCH("/workspaces/{workspace_id}", { params: { path: { workspace_id: id } }, body })),
    onSuccess: async (data) => {
      qc.setQueryData(qk.workspace(id), data);
      await qc.invalidateQueries({ queryKey: qk.workspaces });
      await qc.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useDeleteWorkspace(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE("/workspaces/{workspace_id}", { params: { path: { workspace_id: id } } })),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.me });
      await qc.invalidateQueries({ queryKey: qk.workspaces });
    },
  });
}

export function useMembers(ws: string) {
  return useQuery({
    queryKey: qk.members(ws),
    queryFn: () =>
      unwrap(api.GET("/workspaces/{workspace_id}/members", { params: { path: { workspace_id: ws } } })),
  });
}

export function useUpdateMemberRole(ws: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: S["WorkspaceRole"] }) =>
      unwrap(
        api.PATCH("/workspaces/{workspace_id}/members/{user_id}", {
          params: { path: { workspace_id: ws, user_id: userId } },
          body: { role },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.members(ws) }),
  });
}

export function useRemoveMember(ws: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      unwrap(
        api.DELETE("/workspaces/{workspace_id}/members/{user_id}", {
          params: { path: { workspace_id: ws, user_id: userId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.members(ws) }),
  });
}

export function useInvites(ws: string, enabled = true) {
  return useQuery({
    queryKey: qk.invites(ws),
    queryFn: () =>
      unwrap(api.GET("/workspaces/{workspace_id}/invites", { params: { path: { workspace_id: ws } } })),
    enabled,
  });
}

export function useCreateInvite(ws: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["InviteCreate"]) =>
      unwrap(
        api.POST("/workspaces/{workspace_id}/invites", { params: { path: { workspace_id: ws } }, body }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.invites(ws) }),
  });
}

export function useRevokeInvite(ws: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inviteId: string) =>
      unwrap(
        api.DELETE("/workspaces/{workspace_id}/invites/{invite_id}", {
          params: { path: { workspace_id: ws, invite_id: inviteId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.invites(ws) }),
  });
}

export function useResendInvite(ws: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inviteId: string) =>
      unwrap(
        api.POST("/workspaces/{workspace_id}/invites/{invite_id}/resend", {
          params: { path: { workspace_id: ws, invite_id: inviteId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.invites(ws) }),
  });
}

export function useWorkspaceUsage(ws: string) {
  return useQuery({
    queryKey: qk.usage(ws),
    queryFn: () =>
      unwrap(api.GET("/workspaces/{workspace_id}/usage", { params: { path: { workspace_id: ws } } })),
    staleTime: 30_000,
  });
}

// ---- notifications --------------------------------------------------------------------------

export function useNotifications(enabled = true) {
  return useInfiniteQuery({
    queryKey: qk.notifications,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/notifications", {
          params: { query: { limit: 20, ...(pageParam ? { cursor: pageParam } : {}) } },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    enabled,
    refetchInterval: 60_000,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/notifications/{notification_id}/read", { params: { path: { notification_id: id } } }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.notifications }),
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/notifications/read-all")),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.notifications }),
  });
}

// ---- GPUs / queue / jobs --------------------------------------------------------------------

export function useGpus(refetchMs: number | false = 10_000) {
  return useQuery({ queryKey: qk.gpus, queryFn: () => unwrap(api.GET("/gpus")), refetchInterval: refetchMs });
}

export function useQueue(refetchMs: number | false = 15_000) {
  return useQuery({
    queryKey: qk.queue,
    queryFn: () => unwrap(api.GET("/queue")),
    refetchInterval: refetchMs,
  });
}

const ACTIVE_JOB: readonly S["JobStatus"][] = ["queued", "running"];

export function useJob(id: string | null | undefined) {
  return useQuery({
    queryKey: qk.job(id ?? ""),
    queryFn: () => unwrap(api.GET("/jobs/{job_id}", { params: { path: { job_id: id ?? "" } } })),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && ACTIVE_JOB.includes(q.state.data.status) ? 3000 : false),
  });
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/jobs/{job_id}/cancel", { params: { path: { job_id: id } } })),
    onSuccess: (job) => {
      qc.setQueryData(qk.job(job.id), job);
    },
  });
}
