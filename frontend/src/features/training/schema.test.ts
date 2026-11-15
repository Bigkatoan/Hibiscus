import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import actJson from "../../../../api/policy-schemas/act.json";
import presetsJson from "../../../../api/policy-schemas/presets.json";
import trainJson from "../../../../api/policy-schemas/train.json";
import {
  asSchema,
  buildRequestConfig,
  checkCrossFieldRules,
  deepMerge,
  groupFields,
  presetBase,
  schemaDefaults,
  validateValues,
  widgetFor,
  type JsonObject,
} from "./schema";

const act = asSchema(actJson);
const train = asSchema(trainJson);
const quick = presetsJson.presets.find((p) => p.id === "quick");
if (!quick) throw new Error("quick preset missing");

const schemaDir = resolve(__dirname, "../../../../api/policy-schemas");
const allPolicySchemas = readdirSync(schemaDir)
  .filter((f) => !["index.json", "presets.json", "train.json"].includes(f))
  .map((f) => [f, asSchema(JSON.parse(readFileSync(resolve(schemaDir, f), "utf8")))] as const);

describe("policy schema helpers (real LeRobot 0.7.1 schemas)", () => {
  it("collects defaults", () => {
    const d = schemaDefaults(act);
    expect(d.chunk_size).toBe(100);
    expect(d.vision_backbone).toBe("resnet18");
    expect(d.normalization_mapping).toEqual({ VISUAL: "MEAN_STD", STATE: "MEAN_STD", ACTION: "MEAN_STD" });
    expect(schemaDefaults(train).steps).toBe(100000);
  });

  it("orders basic fields by x-hibiscus.basic_order", () => {
    const g = groupFields(act);
    expect(g.basic.map((f) => f.name)).toEqual([
      "chunk_size",
      "n_action_steps",
      "use_vae",
      "kl_weight",
      "dim_model",
      "optimizer_lr",
      "vision_backbone",
    ]);
    expect(g.advanced.some((f) => f.name === "n_obs_steps")).toBe(true);
    expect(g.basic.every((f) => f.cli?.startsWith("--policy."))).toBe(true);
  });

  it("applies the preset on top of defaults", () => {
    const base = presetBase(act, train, quick);
    expect(base.train.steps).toBe(10000);
    expect(base.train.save_freq).toBe(5000);
    expect(base.train.mixed_precision).toBe("no");
    expect(base.policy.chunk_size).toBe(100);
  });

  it("schema defaults validate against their own schema for every policy and train.json", () => {
    for (const [name, s] of [...allPolicySchemas, ["train.json", train] as const]) {
      const issues = validateValues(schemaDefaults(s), s);
      expect({ name, issues }).toEqual({ name, issues: [] });
    }
  });

  it("chooses a widget for every property of every policy (no unsupported shapes)", () => {
    const kinds = new Set<string>();
    for (const [, s] of [...allPolicySchemas, ["train", train] as const]) {
      for (const p of Object.values(s.properties ?? {})) kinds.add(widgetFor(p).kind);
    }
    expect(kinds.has("boolean")).toBe(true);
    expect(kinds.has("integer")).toBe(true);
    expect(kinds.has("enum")).toBe(true);
    expect(kinds.has("tuple")).toBe(true);
    expect(kinds.has("dict-enum")).toBe(true);
    expect(kinds.has("nullable-object")).toBe(true); // train.peft
  });

  it("maps specific shapes", () => {
    const p = act.properties ?? {};
    expect(widgetFor(p.pretrained_backbone_weights ?? {})).toMatchObject({ kind: "string", nullable: true });
    expect(widgetFor(p.replace_final_stride_with_dilation ?? {}).kind).toBe("boolean");
    expect(widgetFor(p.temporal_ensemble_coeff ?? {})).toMatchObject({ kind: "number", nullable: true });
    expect(widgetFor(train.properties?.mixed_precision ?? {}).kind).toBe("enum");
    expect(widgetFor(train.properties?.peft ?? {})).toMatchObject({
      kind: "nullable-object",
      nullable: true,
    });
  });

  it("reports schema violations by field", () => {
    const values: JsonObject = { ...schemaDefaults(act), chunk_size: 0, vision_backbone: "vit_b", bogus: 1 };
    const issues = validateValues(values, act);
    const byField = new Map(issues.map((i) => [i.field, i.keyword]));
    expect(byField.get("chunk_size")).toBe("minimum");
    expect(byField.get("vision_backbone")).toBe("pattern");
    expect(byField.get("bogus")).toBe("additionalProperties");
    const tr = validateValues({ ...schemaDefaults(train), batch_size: 0, mixed_precision: "fp8" }, train);
    expect(tr.map((i) => i.field).sort()).toEqual(["batch_size", "mixed_precision"]);
  });

  it("evaluates simple cross-field rules (n_action_steps <= chunk_size)", () => {
    expect(checkCrossFieldRules({ chunk_size: 50, n_action_steps: 100 }, act)).toEqual([
      {
        field: "n_action_steps",
        keyword: "cross_field",
        params: { rule: "n_action_steps <= chunk_size", other: "chunk_size" },
      },
    ]);
    expect(checkCrossFieldRules({ chunk_size: 100, n_action_steps: 50 }, act)).toEqual([]);
  });

  it("request payload = full basic set + changed advanced values", () => {
    const base = presetBase(act, train, quick);
    const values = {
      policy: { ...base.policy, chunk_size: 50, n_action_steps: 50, dropout: 0.2 },
      train: { ...base.train, batch_size: 16 },
    };
    const req = buildRequestConfig(values, base, act, train);
    expect(Object.keys(req.policy).sort()).toEqual(
      [
        "chunk_size",
        "dim_model",
        "dropout",
        "kl_weight",
        "n_action_steps",
        "optimizer_lr",
        "use_vae",
        "vision_backbone",
      ].sort(),
    );
    expect(req.policy.dropout).toBe(0.2);
    expect(req.train.batch_size).toBe(16);
    expect(req.train.steps).toBe(10000);
    expect(req.train).not.toHaveProperty("num_workers");
  });

  it("deepMerge merges objects and replaces arrays", () => {
    expect(deepMerge({ a: { b: 1, c: [1, 2] }, d: 1 }, { a: { c: [3] }, e: undefined })).toEqual({
      a: { b: 1, c: [3] },
      d: 1,
    });
  });
});
