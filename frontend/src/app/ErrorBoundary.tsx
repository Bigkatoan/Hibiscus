import { Component, type ErrorInfo, type ReactNode } from "react";
import { useRouteError } from "react-router-dom";
import { Mascot } from "@/components/Mascot";
import { Button } from "@/components/ui/button";
import { i18n } from "@/lib/i18n";

const FALLBACK_COPY: Record<string, string> = {
  "crash.title": "Something went wrong",
  "crash.description": "Reload to try again; if it keeps happening, tell your administrator.",
  "crash.reload": "Reload",
  "crash.home": "Go to the home page",
};

/** Translate without trusting i18n (it may be the thing that failed). */
function tr(key: string): string {
  try {
    const v = i18n.isInitialized ? i18n.t(key) : "";
    if (v && v !== key) return v;
  } catch {
    /* fall through */
  }
  return FALLBACK_COPY[key] ?? key;
}

/** Pixel-styled crash screen: sad Hibi on the garden background, reload + home actions. */
export function CrashFallback({ error }: { error?: unknown }) {
  const detail = error instanceof Error ? error.message : null;
  return (
    <main
      id="main"
      role="alert"
      data-testid="crash-fallback"
      className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-12 text-center text-foreground"
    >
      <Mascot mood="sad" />
      <h1 className="mt-4 font-extrabold text-xl">{tr("crash.title")}</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{tr("crash.description")}</p>
      {detail ? (
        <pre className="mt-3 max-w-md whitespace-pre-wrap text-xs text-muted-foreground [overflow-wrap:anywhere]">
          {detail}
        </pre>
      ) : null}
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <Button
          onClick={() => {
            window.location.reload();
          }}
        >
          {tr("crash.reload")}
        </Button>
        <Button variant="secondary" asChild>
          <a href="/">{tr("crash.home")}</a>
        </Button>
      </div>
    </main>
  );
}

interface State {
  error: unknown;
}

/** Top-level boundary: a render error anywhere shows the crash screen instead of a blank page. */
export class AppErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error: error ?? new Error("unknown error") };
  }

  override componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error("Hibiscus UI crashed", error, info.componentStack);
  }

  override render(): ReactNode {
    if (this.state.error) return <CrashFallback error={this.state.error} />;
    return this.props.children;
  }
}

/** React Router errorElement: route render errors are caught by the router, not by the boundary. */
export function RouteErrorFallback() {
  const error = useRouteError();
  return <CrashFallback error={error} />;
}
