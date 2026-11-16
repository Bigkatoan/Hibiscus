import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import Ajv2020 from "ajv/dist/2020";
import { afterEach, describe, expect, it, vi } from "vitest";
import { validate } from "./jsonSchema";

const schemaDir = resolve(__dirname, "../../../../api/policy-schemas");
const schemas = readdirSync(schemaDir)
  .filter((f) => !["index.json", "presets.json"].includes(f))
  .map(
    (f) => [f, JSON.parse(readFileSync(resolve(schemaDir, f), "utf8")) as Record<string, unknown>] as const,
  );

function defaults(s: Record<string, unknown>): Record<string, unknown> {
  const props = (s.properties ?? {}) as Record<string, { default?: unknown }>;
  return Object.fromEntries(
    Object.entries(props)
      .filter(([, p]) => p.default !== undefined)
      .map(([k, p]) => [k, structuredClone(p.default)]),
  );
}

/** Mutations that exercise every keyword the real schemas use. */
function mutations(s: Record<string, unknown>): Record<string, unknown>[] {
  const base = defaults(s);
  const out: Record<string, unknown>[] = [base, { ...base, __bogus__: 1 }];
  for (const [k, v] of Object.entries(base)) {
    out.push({ ...base, [k]: null });
    out.push({ ...base, [k]: "x" });
    out.push({ ...base, [k]: -1 });
    out.push({ ...base, [k]: 0 });
    out.push({ ...base, [k]: 1.5 });
    out.push({ ...base, [k]: [] });
    out.push({ ...base, [k]: [1, 2, 3] });
    out.push({ ...base, [k]: {} });
    if (Array.isArray(v)) out.push({ ...base, [k]: [...(v as unknown[]), ...(v as unknown[])] });
  }
  return out;
}

describe("CSP-safe JSON Schema validator", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("agrees with Ajv 2020-12 (valid/invalid + failing fields) on every policy schema", () => {
    const ajv = new Ajv2020({ strict: false, allErrors: true, validateFormats: false });
    for (const [name, raw] of schemas) {
      const copy = { ...raw };
      delete copy.$id;
      delete copy.$schema;
      const fn = ajv.compile(copy);
      for (const value of mutations(raw)) {
        const ajvOk = fn(value);
        const ours = validate(raw, value);
        expect({ name, value, ok: ours.length === 0 }).toEqual({ name, value, ok: ajvOk });
        const top = (path: string) => path.replace(/^\//, "").split("/")[0] ?? "";
        const ajvFields = new Set((fn.errors ?? []).map((e) => top(e.instancePath)));
        const ourFields = new Set(ours.map((e) => top(e.instancePath)));
        expect({ name, fields: [...ourFields].sort() }).toEqual({ name, fields: [...ajvFields].sort() });
      }
    }
  });

  it("covers keywords the schemas may use", () => {
    const s = {
      type: "object",
      required: ["a"],
      properties: {
        a: { type: "integer", exclusiveMinimum: 0, multipleOf: 2 },
        b: { type: "string", minLength: 2, maxLength: 3, pattern: "^[a-z]+$" },
        c: {
          type: "array",
          prefixItems: [{ type: "integer" }],
          items: { type: "string" },
          uniqueItems: true,
        },
        d: { oneOf: [{ type: "integer" }, { type: "number" }] },
        e: { not: { const: 5 } },
        f: { allOf: [{ minimum: 1 }, { maximum: 3 }] },
      },
      additionalProperties: { type: "boolean" },
    };
    expect(validate(s, { a: 2, b: "ab", c: [1, "x"], d: 1.5, e: 4, f: 2, g: true })).toEqual([]);
    const kw = (v: unknown) => validate(s, v).map((e) => `${e.instancePath}:${e.keyword}`);
    expect(kw({})).toEqual([":required"]);
    expect(kw({ a: 0 })).toEqual(["/a:exclusiveMinimum"]);
    expect(kw({ a: 3 })).toEqual(["/a:multipleOf"]);
    expect(kw({ a: 2, b: "A" })).toEqual(["/b:minLength", "/b:pattern"]);
    expect(kw({ a: 2, c: ["x"] })).toEqual(["/c/0:type"]);
    expect(kw({ a: 2, c: [1, "x", "x"] })).toEqual(["/c:uniqueItems"]);
    expect(kw({ a: 2, d: 1 })).toEqual(["/d:oneOf"]);
    expect(kw({ a: 2, e: 5 })).toEqual(["/e:not"]);
    expect(kw({ a: 2, f: 4 })).toEqual(["/f:maximum"]);
    expect(kw({ a: 2, g: 1 })).toEqual(["/g:type"]);
  });

  it("runs with eval and new Function disabled (production CSP: script-src 'self')", async () => {
    const blocked = () => {
      throw new EvalError("Refused to evaluate a string as JavaScript (unsafe-eval)");
    };
    vi.stubGlobal("eval", blocked);
    vi.stubGlobal("Function", new Proxy(Function, { construct: blocked, apply: blocked }));
    // Also block the Function constructor reachable through any function's prototype.
    const proto = Object.getPrototypeOf(() => undefined) as { constructor: unknown };
    const original = proto.constructor;
    Object.defineProperty(proto, "constructor", { value: blocked, configurable: true, writable: true });
    try {
      // eslint-disable-next-line @typescript-eslint/no-implied-eval -- asserting the block works
      expect(() => new globalThis.Function("return 1")).toThrow(EvalError);
      vi.resetModules();
      const mod = await import("./schema");
      for (const [name, raw] of schemas) {
        const s = mod.asSchema(raw);
        expect({ name, issues: mod.validateValues(mod.schemaDefaults(s), s) }).toEqual({ name, issues: [] });
        const bad = mod.validateValues({ ...mod.schemaDefaults(s), __bogus__: 1 }, s);
        expect(bad.some((i) => i.field === "__bogus__")).toBe(true);
      }
    } finally {
      Object.defineProperty(proto, "constructor", { value: original, configurable: true, writable: true });
    }
  });

  it("no app (non-test) source imports Ajv or generates code at runtime", () => {
    const root = resolve(__dirname, "../..");
    const files: string[] = [];
    const visit = (dir: string) => {
      for (const f of readdirSync(dir)) {
        const p = join(dir, f);
        if (statSync(p).isDirectory()) {
          if (!["test", "generated"].includes(f)) visit(p);
        } else if (/\.(ts|tsx)$/.test(f) && !/\.test\.tsx?$/.test(f)) files.push(p);
      }
    };
    visit(root);
    const offenders = files.filter((f) => {
      const src = readFileSync(f, "utf8");
      return /from\s+["']ajv/.test(src) || /new Function\s*\(/.test(src) || /\beval\s*\(/.test(src);
    });
    expect(offenders).toEqual([]);
  });
});
