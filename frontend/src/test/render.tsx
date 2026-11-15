import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router-dom";
import { SessionWatcher } from "@/app/guards";
import { routes } from "@/app/routes";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";

export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

export function Providers({ children, client }: { children: ReactNode; client: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <TooltipProvider delayDuration={0}>{children}</TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export interface RenderRouteOptions {
  path?: string;
  url?: string;
  extraRoutes?: RouteObject[];
  client?: QueryClient;
}

/** Render the real application route tree at `url` (AppShell, guards, workspace resolution). */
export function renderApp(url: string, client: QueryClient = testQueryClient()) {
  const router = createMemoryRouter(routes, {
    initialEntries: [url],
    future: { v7_relativeSplatPath: true },
  });
  const result = render(
    <Providers client={client}>
      <SessionWatcher />
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </Providers>,
  );
  return { ...result, client, router };
}

/** Render `element` mounted at `path`, navigated to `url`, with all app providers. */
export function renderRoute(
  element: ReactElement,
  { path = "/", url = "/", extraRoutes = [], client = testQueryClient() }: RenderRouteOptions = {},
): RenderResult & { client: QueryClient; router: ReturnType<typeof createMemoryRouter> } {
  const router = createMemoryRouter(
    [{ path, element }, ...extraRoutes, { path: "*", element: <div>not-found-route</div> }],
    {
      initialEntries: [url],
      future: { v7_relativeSplatPath: true },
    },
  );
  const result = render(
    <Providers client={client}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </Providers>,
  );
  return { ...result, client, router };
}
