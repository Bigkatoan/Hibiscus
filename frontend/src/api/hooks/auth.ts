import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, unwrap, type Schemas } from "../client";
import { qk } from "./keys";

type S = Schemas;

/** GET /auth/me (getMe). Resolves to null when unauthenticated (401). */
export function useMe() {
  return useQuery({
    queryKey: qk.me,
    queryFn: async (): Promise<S["Me"] | null> => {
      try {
        return await unwrap(api.GET("/auth/me"));
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useAuthConfig() {
  return useQuery({
    queryKey: qk.authConfig,
    queryFn: () => unwrap(api.GET("/auth/config")),
    staleTime: 5 * 60_000,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["LoginRequest"]) => unwrap(api.POST("/auth/login", { body })),
    onSuccess: async (res) => {
      if (res.status === "ok") await qc.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useLoginSecondFactor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["LoginSecondFactorRequest"]) => unwrap(api.POST("/auth/login/2fa", { body })),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/auth/logout")),
    onSettled: () => {
      qc.setQueryData(qk.me, null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" && q.queryKey[0] !== "auth-config" });
    },
  });
}

export function useForgotPassword() {
  return useMutation({
    mutationFn: (body: S["ForgotPasswordRequest"]) => unwrap(api.POST("/auth/password/forgot", { body })),
  });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: (body: S["ResetPasswordRequest"]) => unwrap(api.POST("/auth/password/reset", { body })),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: S["ChangePasswordRequest"]) => unwrap(api.POST("/auth/password/change", { body })),
  });
}

export function useVerifyEmail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => unwrap(api.POST("/auth/email/verify", { body: { token } })),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useResendVerification() {
  return useMutation({ mutationFn: () => unwrap(api.POST("/auth/email/resend")) });
}

export function useInvitePreview(token: string | null) {
  return useQuery({
    queryKey: qk.invite(token ?? ""),
    // Token in the body, never in the URL path (access logs, CR-BE-S1).
    queryFn: () => unwrap(api.POST("/auth/invites/preview", { body: { token: token ?? "" } })),
    enabled: !!token,
    retry: false,
  });
}

export function useRegisterWithInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["RegisterInviteRequest"]) => unwrap(api.POST("/auth/register-invite", { body })),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useAcceptInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => unwrap(api.POST("/auth/invites/accept", { body: { token } })),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.me });
      await qc.invalidateQueries({ queryKey: qk.workspaces });
    },
  });
}

// ---- 2FA ------------------------------------------------------------------------------------

export function useTotpSetup() {
  return useMutation({
    mutationFn: (password: string) => unwrap(api.POST("/auth/2fa/totp/setup", { body: { password } })),
  });
}

export function useTotpEnable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => unwrap(api.POST("/auth/2fa/totp/enable", { body: { code } })),
    onSuccess: async () => {
      // Enabling 2FA revokes every personal access token of the user (SEC-auth-01).
      await Promise.all([
        qc.invalidateQueries({ queryKey: qk.me }),
        qc.invalidateQueries({ queryKey: qk.tokens }),
      ]);
    },
  });
}

export function useTotpDisable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["TotpDisableRequest"]) => unwrap(api.POST("/auth/2fa/totp/disable", { body })),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useRegenerateRecoveryCodes() {
  return useMutation({
    mutationFn: (code: string) => unwrap(api.POST("/auth/2fa/recovery-codes", { body: { code } })),
  });
}

// ---- sessions & PATs ------------------------------------------------------------------------

export function useSessions() {
  return useQuery({ queryKey: qk.sessions, queryFn: () => unwrap(api.GET("/auth/sessions")) });
}

export function useRevokeSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      unwrap(api.DELETE("/auth/sessions/{session_id}", { params: { path: { session_id: sessionId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.sessions }),
  });
}

export function useRevokeOtherSessions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/auth/sessions/revoke-others")),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.sessions }),
  });
}

export function useApiTokens() {
  return useQuery({ queryKey: qk.tokens, queryFn: () => unwrap(api.GET("/auth/tokens")) });
}

export function useCreateApiToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["ApiTokenCreate"]) => unwrap(api.POST("/auth/tokens", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.tokens }),
  });
}

export function useRevokeApiToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tokenId: string) =>
      unwrap(api.DELETE("/auth/tokens/{token_id}", { params: { path: { token_id: tokenId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.tokens }),
  });
}

// ---- profile & secrets ----------------------------------------------------------------------

export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["UserUpdate"]) => unwrap(api.PATCH("/users/me", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.me }),
  });
}

export function useHfTokenStatus() {
  return useQuery({ queryKey: qk.hfToken, queryFn: () => unwrap(api.GET("/users/me/secrets/hf-token")) });
}

export function useSetHfToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => unwrap(api.PUT("/users/me/secrets/hf-token", { body: { token } })),
    onSuccess: (data) => {
      qc.setQueryData(qk.hfToken, data);
    },
  });
}

export function useDeleteHfToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/users/me/secrets/hf-token")),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.hfToken }),
  });
}

export function useNotificationChannels() {
  return useQuery({
    queryKey: qk.channels,
    queryFn: () => unwrap(api.GET("/users/me/notification-channels")),
  });
}

export function useCreateNotificationChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["NotificationChannelCreate"]) =>
      unwrap(api.POST("/users/me/notification-channels", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.channels }),
  });
}

export function useDeleteNotificationChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/users/me/notification-channels/{channel_id}", { params: { path: { channel_id: id } } }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.channels }),
  });
}

export function useTestNotificationChannel() {
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/users/me/notification-channels/{channel_id}/test", {
          params: { path: { channel_id: id } },
        }),
      ),
  });
}
