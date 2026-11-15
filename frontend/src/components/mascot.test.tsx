import { render, screen } from "@testing-library/react";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import { PxIcon, Sprite } from "@/hibiscus/PixelAnim";
import { ANIMS } from "@/hibiscus/sprites.gen";
import { HIBI_MOODS, hibiForRunStatus, RUN_HIBI } from "@/lib/hibi";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, server } from "@/test/server";
import { Mascot } from "./Mascot";

describe("Hibi mascot (hibiscus-assets)", () => {
  it("maps the four core run states to the style guide's moods", () => {
    expect(hibiForRunStatus("queued")).toBe("sleep");
    expect(hibiForRunStatus("running")).toBe("working");
    expect(hibiForRunStatus("succeeded")).toBe("happy");
    expect(hibiForRunStatus("failed")).toBe("sad");
  });

  it("has a drawn mood for every run status in the contract, in both resolutions", () => {
    const all: Schemas["RunStatus"][] = [
      "queued",
      "preparing",
      "running",
      "pausing",
      "paused",
      "exporting",
      "succeeded",
      "failed",
      "cancelling",
      "cancelled",
    ];
    for (const s of all) expect(HIBI_MOODS).toContain(RUN_HIBI[s]);
    for (const m of HIBI_MOODS) {
      expect(Object.keys(ANIMS)).toContain(`hibi_${m}`);
      expect(Object.keys(ANIMS)).toContain(`hibi_mini_${m}`);
    }
  });

  it("draws the robot-arm Hibi strip at one art pixel = 2 CSS px", () => {
    const { container, rerender } = render(<Mascot mood="wave" label="Hibi" />);
    const hero = screen.getByRole("img", { name: "Hibi" });
    expect(hero).toHaveClass("px-anim");
    expect(hero.style.getPropertyValue("--src")).toBe("url(/pixel/anim/hibi_wave.png)");
    expect(container.querySelector("[data-hibi='wave']")).not.toBeNull();
    rerender(<Mascot mood="sad" size="mini" />);
    const mini = container.querySelector<HTMLElement>(".px-anim")!;
    expect(mini.style.getPropertyValue("--src")).toBe("url(/pixel/anim/hibi_mini_sad.png)");
    expect(mini).toHaveAttribute("aria-hidden", "true");
  });

  it("static sprites and glyphs have no per-use scale: 16×16 → 32 px, 8×8 → 16 px", () => {
    render(
      <>
        <Sprite name="icon_camera" alt="camera" />
        <PxIcon name="estop" label="stop" />
      </>,
    );
    const img = screen.getByRole("img", { name: "camera" });
    expect(img).toHaveAttribute("width", "32");
    expect(img).toHaveAttribute("height", "32");
    expect(img).toHaveClass("pixelated");
    const glyph = screen.getByRole("img", { name: "stop" });
    expect(glyph).toHaveAttribute("width", "16");
  });

  it.each([
    ["running", "working"],
    ["failed", "sad"],
    ["queued", "sleep"],
    ["succeeded", "happy"],
  ] as const)("run detail shows Hibi %s → %s", async (status, mood) => {
    server.use(http.get("/runs/{run_id}", () => HttpResponse.json({ ...f.run, status })));
    const { container } = renderApp(`/w/robot-lab/runs/${f.IDS.run}`);
    expect(await screen.findByTestId("run-hibi")).toBeInTheDocument();
    expect(container.querySelector(`[data-hibi="${mood}"]`)).not.toBeNull();
  });
});
