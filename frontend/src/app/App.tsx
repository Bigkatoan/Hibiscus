import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { ApiError } from "@/api/client";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";
import { SessionWatcher } from "./guards";
import { routes } from "./routes";

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache(),
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: true,
        // Never retry client errors (4xx); retry network/5xx twice.
        retry: (count, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      },
      mutations: { retry: false },
    },
  });
}

const queryClient = makeQueryClient();
export const ROUTER_FUTURE = { v7_relativeSplatPath: true } as const;
const router = createBrowserRouter(routes, { future: ROUTER_FUTURE });

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TooltipProvider delayDuration={300}>
          <SessionWatcher />
          <RouterProvider router={router} future={{ v7_startTransition: true }} />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
