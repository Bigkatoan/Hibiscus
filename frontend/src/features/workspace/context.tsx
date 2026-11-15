import { createContext, useContext } from "react";
import { Navigate, Outlet, useParams } from "react-router-dom";
import type { Schemas } from "@/api/client";
import { useMe } from "@/api/hooks/auth";
import { PageLoader } from "@/components/common";
import { NotFoundPage } from "@/features/misc/NotFoundPage";

export type Membership = Schemas["Membership"];
export type WorkspaceRole = Schemas["WorkspaceRole"];

const RANK: Record<WorkspaceRole, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };

export function roleAtLeast(role: WorkspaceRole, min: WorkspaceRole): boolean {
  return RANK[role] >= RANK[min];
}

const WorkspaceContext = createContext<Membership | null>(null);

export function WorkspaceProvider({ value, children }: { value: Membership; children: React.ReactNode }) {
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

/** Route element for `/w/:slug/*`: resolves the slug against the caller's memberships. */
export function WorkspaceRoute() {
  const { slug } = useParams();
  const me = useMe();
  if (me.isPending) return <PageLoader />;
  const membership = me.data?.memberships.find((m) => m.workspace_slug === slug);
  if (!membership) return <NotFoundPage />;
  return (
    <WorkspaceProvider value={membership}>
      <Outlet />
    </WorkspaceProvider>
  );
}

export function useWorkspace(): Membership {
  const ws = useContext(WorkspaceContext);
  if (!ws) throw new Error("useWorkspace must be used under /w/:slug");
  return ws;
}

export function useOptionalWorkspace(): Membership | null {
  return useContext(WorkspaceContext);
}

export function useCan(min: WorkspaceRole): boolean {
  const ws = useContext(WorkspaceContext);
  return ws ? roleAtLeast(ws.role, min) : false;
}

/** Path helper: `/w/<slug>/<rest>`. */
export function useWsPath(): (rest: string) => string {
  const ws = useWorkspace();
  return (rest) => `/w/${ws.workspace_slug}/${rest.replace(/^\//, "")}`;
}

/** `/` => first workspace (by name), or an empty-state page if the user has none. */
export function HomeRedirect() {
  const me = useMe();
  if (me.isPending) return <PageLoader />;
  const first = [...(me.data?.memberships ?? [])].sort((a, b) =>
    a.workspace_name.localeCompare(b.workspace_name),
  )[0];
  if (!first) return <Navigate to="/no-workspace" replace />;
  return <Navigate to={`/w/${first.workspace_slug}/datasets`} replace />;
}
