import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import en from "@/i18n/en/translation.json";
import vi from "@/i18n/vi/translation.json";
import { i18n } from "@/lib/i18n";
import * as f from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { http, server } from "@/test/server";
import { asSchema, autoLogFreq, followLogFreq, groupFields } from "./schema";

type Tree = { [k: string]: string | Tree };
function lookup(tree: Tree, key: string): string | undefined {
  let node: string | Tree | undefined = tree;
  for (const part of key.split(".")) {
    if (typeof node !== "object") return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

const schemaDir = resolve(__dirname, "../../../../api/policy-schemas");
const policyFiles = readdirSync(schemaDir).filter(
  (f) => !["index.json", "presets.json", "train.json"].includes(f),
);

function fieldBox(name: string): HTMLElement {
  const el = document.querySelector<HTMLElement>(`[data-field="${name}"]`);
  if (!el) throw new Error(`field ${name} not rendered`);
  return el;
}

describe("wizard copy and behaviour (CX-04, CX-10, QC-e2e-11)", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("every basic field of every policy (and train.json) has a vi + en label and help text", () => {
    const missing: string[] = [];
    const check = (prefix: string, file: string) => {
      const schema = asSchema(JSON.parse(readFileSync(resolve(schemaDir, file), "utf8")));
      for (const fld of groupFields(schema).basic)
        for (const part of ["label", "help"])
          for (const [lng, tree] of [
            ["vi", vi],
            ["en", en],
          ] as const) {
            const key = `${prefix}.${fld.name}.${part}`;
            if (!lookup(tree, key)) missing.push(`${lng}:${key}`);
          }
    };
    check("train", "train.json");
    for (const file of policyFiles) check(`policy.${file.replace(".json", "")}`, file);
    expect(missing).toEqual([]);
  });

  it("Vietnamese UI: the params step shows Vietnamese labels/help, the --flag stays for experts", async () => {
    server.use(
      http.get("/auth/me", () => HttpResponse.json({ ...f.me, user: { ...f.me.user, locale: "vi" } })),
    );
    await i18n.changeLanguage("vi");
    renderApp(`/w/robot-lab/runs/new?version=${f.IDS.version}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Tiếp/ }));
    expect(await screen.findByText("Số action thực thi mỗi lần dự đoán")).toBeInTheDocument();
    expect(screen.getByText("Số bước train")).toBeInTheDocument();
    expect(screen.queryByText(/The number of action steps to run/)).toBeNull();
    expect(screen.queryByText(/Set this flag to `true`/)).toBeNull();
    expect(within(fieldBox("n_action_steps")).getByText("--policy.n_action_steps")).toBeInTheDocument();
    // Mobile stepper: the current step carries "3/4" (CX-10).
    const current = document.querySelector('[aria-current="step"]');
    expect(current).toHaveTextContent("Tham số");
    expect(current).toHaveTextContent("3/4");
  });

  it("lowering steps lowers log_freq so short runs get chart points", () => {
    const base = { steps: 10000, log_freq: 100 };
    expect(autoLogFreq(200, 100)).toBe(20);
    expect(autoLogFreq(50, 100)).toBe(10);
    expect(autoLogFreq(5000, 100)).toBe(100);
    const short = followLogFreq(base, { ...base, steps: 200 }, base);
    expect(short.log_freq).toBe(20);
    // back up again: still automatic
    expect(followLogFreq(short, { ...short, steps: 10000 }, base).log_freq).toBe(100);
    // a log_freq the user typed is left alone
    const manual = { steps: 10000, log_freq: 50 };
    expect(followLogFreq(manual, { ...manual, steps: 200 }, base).log_freq).toBe(50);
  });
});
