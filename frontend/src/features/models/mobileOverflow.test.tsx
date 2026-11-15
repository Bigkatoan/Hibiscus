import { screen } from "@testing-library/react";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, server } from "@/test/server";

/**
 * QC N-1 / CX-10 at 390 px. jsdom has no layout, so these pin the CSS contract that keeps wide
 * content inside its own scroller instead of widening the page: long unbreakable names may wrap
 * anywhere, wide tables sit in an overflow-x-auto wrapper, and grid/flex ancestors can shrink.
 */
const LONG = "picknplace_20261114_2217_act_r1_step300000_with_a_very_long_unbroken_name";

function hasClass(el: Element | null, cls: string): boolean {
  return !!el && el.classList.contains(cls);
}

describe("390 px overflow (QC N-1)", () => {
  it("model page: long title wraps and the files table scrolls in its own box", async () => {
    server.use(http.get("/models/{model_id}", () => HttpResponse.json({ ...f.model, name: LONG })));
    renderApp(`/w/robot-lab/models/${f.IDS.model}`);
    const title = await screen.findByText(LONG, { selector: "h1 span span" });
    expect(hasClass(title, "[overflow-wrap:anywhere]")).toBe(true);
    expect(hasClass(title, "min-w-0")).toBe(true);
    const h1 = title.closest("h1");
    expect(hasClass(h1, "[overflow-wrap:anywhere]")).toBe(true);

    const table = (await screen.findByText(/model\.safetensors/)).closest("table");
    expect(table).not.toBeNull();
    expect(hasClass(table!.parentElement, "overflow-x-auto")).toBe(true);
    // The two-card grid must use minmax(0,1fr) columns at phone width, not `auto`.
    const grids = document.querySelectorAll("main .grid.lg\\:grid-cols-2");
    expect(grids.length).toBeGreaterThan(0);
    grids.forEach((g) => {
      expect(hasClass(g, "grid-cols-1")).toBe(true);
    });
  });

  it("run page: the tab strip (incl. the config tab) scrolls inside a shrinkable container", async () => {
    renderApp(`/w/robot-lab/runs/${f.IDS.run}?tab=config`);
    const configTab = await screen.findByRole("tab", { name: "Config" });
    const list = configTab.closest("[role='tablist']");
    expect(hasClass(list, "overflow-x-auto")).toBe(true);
    expect(hasClass(list, "max-w-full")).toBe(true);
    const wrapper = list!.parentElement;
    expect(hasClass(wrapper, "min-w-0")).toBe(true);
    expect(hasClass(wrapper, "w-full")).toBe(true);
    // Every ancestor up to <main> may shrink below its content width.
    const tabsRoot = wrapper!.parentElement;
    expect(hasClass(tabsRoot, "min-w-0")).toBe(true);
    expect(hasClass(tabsRoot!.parentElement, "min-w-0")).toBe(true);
    expect(hasClass(configTab.closest("main"), "min-w-0")).toBe(true);
  });
});
