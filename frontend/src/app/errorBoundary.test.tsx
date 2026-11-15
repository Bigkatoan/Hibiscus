import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { routes } from "./routes";
import { AppErrorBoundary, RouteErrorFallback } from "./ErrorBoundary";

function Boom(): never {
  throw new RangeError("Incorrect locale information provided");
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("top-level error boundary (QC N-3)", () => {
  it("renders the pixel crash screen instead of a blank page", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>,
    );
    const box = screen.getByTestId("crash-fallback");
    expect(box).toHaveTextContent("Something went wrong");
    expect(box).toHaveTextContent("Incorrect locale information provided");
    expect(box.querySelector("[data-hibi='sad']")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("route render errors use the same crash screen", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const router = createMemoryRouter(
      [{ errorElement: <RouteErrorFallback />, children: [{ path: "/", element: <Boom /> }] }],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);
    expect(screen.getByTestId("crash-fallback")).toHaveTextContent("Something went wrong");
  });

  it("the app route tree has the crash screen as its root errorElement", () => {
    expect(routes).toHaveLength(1);
    expect(routes[0]?.errorElement).toBeTruthy();
  });
});
