import { Navigate, type RouteObject } from "react-router-dom";
import { AccountPage } from "@/features/account/AccountPage";
import {
  AdminAuditPage,
  AdminGpusPage,
  AdminLayout,
  AdminQuotasPage,
  AdminSystemPage,
  AdminUsersPage,
} from "@/features/admin/AdminPages";
import { AcceptInvitePage } from "@/features/auth/AcceptInvitePage";
import { LoginPage } from "@/features/auth/LoginPage";
import { ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage } from "@/features/auth/PasswordPages";
import { DatasetDetailPage } from "@/features/datasets/DatasetDetailPage";
import { DatasetsPage } from "@/features/datasets/DatasetsPage";
import { GpusPage } from "@/features/gpus/GpusPage";
import { NoWorkspacePage, NotFoundPage } from "@/features/misc/NotFoundPage";
import { ModelDetailPage } from "@/features/models/ModelDetailPage";
import { ModelsPage } from "@/features/models/ModelsPage";
import { ComparePage } from "@/features/runs/ComparePage";
import { RunDetailPage } from "@/features/runs/RunDetailPage";
import { RunsPage } from "@/features/runs/RunsPage";
import { NewRunWizard } from "@/features/training/NewRunWizard";
import { UploadPage } from "@/features/upload/UploadPage";
import { HomeRedirect, WorkspaceRoute } from "@/features/workspace/context";
import { WorkspaceSettingsPage } from "@/features/workspace/WorkspaceSettingsPage";
import { AppShell } from "./AppShell";
import { RouteErrorFallback } from "./ErrorBoundary";
import { GuestOnly, RequireAuth, RequirePlatformAdmin } from "./guards";

/**
 * SPA routes. Links e-mailed by the API (A2) target:
 *   /invite#token=…   /reset-password?token=…   /verify-email?token=…
 * The invite token is kept in the fragment / sessionStorage only (SEC-auth-04); the legacy
 * /invite?token=… and /invite/:token forms are accepted once and scrubbed to /invite.
 */
const appRoutes: RouteObject[] = [
  {
    element: <GuestOnly />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
    ],
  },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  { path: "/verify-email", element: <VerifyEmailPage /> },
  { path: "/invite", element: <AcceptInvitePage /> },
  { path: "/invite/:token", element: <AcceptInvitePage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <HomeRedirect /> },
          { path: "/no-workspace", element: <NoWorkspacePage /> },
          { path: "/account", element: <AccountPage /> },
          { path: "/account/:tab", element: <AccountPage /> },
          {
            path: "/admin",
            element: <RequirePlatformAdmin />,
            children: [
              {
                element: <AdminLayout />,
                children: [
                  { index: true, element: <Navigate to="users" replace /> },
                  { path: "users", element: <AdminUsersPage /> },
                  { path: "audit", element: <AdminAuditPage /> },
                  { path: "quotas", element: <AdminQuotasPage /> },
                  { path: "gpus", element: <AdminGpusPage /> },
                  { path: "system", element: <AdminSystemPage /> },
                ],
              },
            ],
          },
          {
            path: "/w/:slug",
            element: <WorkspaceRoute />,
            children: [
              { index: true, element: <Navigate to="datasets" replace /> },
              { path: "datasets", element: <DatasetsPage /> },
              { path: "datasets/upload", element: <UploadPage /> },
              { path: "datasets/:datasetId", element: <DatasetDetailPage /> },
              { path: "runs", element: <RunsPage /> },
              { path: "runs/new", element: <NewRunWizard /> },
              { path: "runs/compare", element: <ComparePage /> },
              { path: "runs/:runId", element: <RunDetailPage /> },
              { path: "models", element: <ModelsPage /> },
              { path: "models/:modelId", element: <ModelDetailPage /> },
              { path: "gpus", element: <GpusPage /> },
              { path: "settings", element: <WorkspaceSettingsPage /> },
              { path: "settings/:tab", element: <WorkspaceSettingsPage /> },
            ],
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

/** Every route renders inside a pathless root whose errorElement is the pixel crash screen. */
export const routes: RouteObject[] = [{ errorElement: <RouteErrorFallback />, children: appRoutes }];
