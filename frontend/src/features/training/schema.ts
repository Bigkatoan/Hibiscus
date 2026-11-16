/**
 * Pure helpers for the policy/train JSON Schemas (docs/spec/policy-schema.md, ADR-0005):
 * defaults, preset merge, basic/advanced grouping, client-side validation (JSON Schema 2020-12
 * subset, interpreted: no `new Function`, CSP-safe) and the
 * request payload (only values differing from defaults+preset, plus the full basic set).
 */
import { isRecord } from "@/lib/utils";
import { validate, type SchemaError } from "./jsonSchema";

export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };
export type JsonObject = Record<string, Json>;

export interface JsonSchema {
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  additionalProperties?: boolean | JsonSchema;
  items?: JsonSchema;
  prefixItems?: JsonSchema[];
  anyOf?: JsonSchema[];
  enum?: Json[];
  const?: Json;
  default?: Json;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  minItems?: number;
  maxItems?: number;
  pattern?: string;
  description?: string;
  title?: string;
  "x-hibiscus-group"?: "basic" | "advanced";
  "x-hibiscus-cli"?: string;
  "x-hibiscus"?: {
    basic_order?: string[];
    cross_field_rules?: { rule: string; code: string }[];
    policy_type?: string;
  };
}

export function asSchema(value: unknown): JsonSchema {
  return isRecord(value) ? value : {};
}

export function deepClone<T extends Json>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

/** Recursive merge: objects merge key-wise, everything else (incl. arrays) replaces. */
export function deepMerge(base: JsonObject, over: Record<string, unknown>): JsonObject {
  const out: JsonObject = { ...base };
  for (const [k, v] of Object.entries(over)) {
    if (v === undefined) continue;
    const prev = out[k];
    if (isRecord(v) && isRecord(prev)) out[k] = deepMerge(prev, v);
    else out[k] = v as Json;
  }
  return out;
}

export function jsonEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Top-level defaults of a document schema (`properties.*.default`). */
export function schemaDefaults(schema: JsonSchema): JsonObject {
  const out: JsonObject = {};
  for (const [k, p] of Object.entries(schema.properties ?? {})) {
    if (p.default !== undefined) out[k] = deepClone(p.default);
  }
  return out;
}

export interface FieldSpec {
  name: string;
  schema: JsonSchema;
  group: "basic" | "advanced";
  cli?: string;
}

/** Basic fields in `x-hibiscus.basic_order` (then any other `basic`), advanced alphabetical-stable. */
export function groupFields(schema: JsonSchema): { basic: FieldSpec[]; advanced: FieldSpec[] } {
  const props = Object.entries(schema.properties ?? {});
  const order = schema["x-hibiscus"]?.basic_order ?? [];
  const spec = ([name, s]: [string, JsonSchema]): FieldSpec => ({
    name,
    schema: s,
    group: s["x-hibiscus-group"] === "basic" ? "basic" : "advanced",
    ...(s["x-hibiscus-cli"] ? { cli: s["x-hibiscus-cli"] } : {}),
  });
  const all = props.map(spec);
  const basic = all.filter((f) => f.group === "basic");
  basic.sort((a, b) => {
    const ia = order.indexOf(a.name);
    const ib = order.indexOf(b.name);
    return (ia === -1 ? 1e9 : ia) - (ib === -1 ? 1e9 : ib);
  });
  return { basic, advanced: all.filter((f) => f.group === "advanced") };
}

export function typesOf(s: JsonSchema): string[] {
  if (Array.isArray(s.type)) return s.type;
  if (typeof s.type === "string") return [s.type];
  return [];
}

export type WidgetKind =
  | "boolean"
  | "integer"
  | "number"
  | "enum"
  | "string"
  | "tuple"
  | "list"
  | "dict-enum"
  | "nullable-object"
  | "json";

export interface Widget {
  kind: WidgetKind;
  nullable: boolean;
  /** Effective non-null schema for scalar/array/object widgets. */
  inner: JsonSchema;
}

/** Decide how to render a property schema. */
export function widgetFor(s: JsonSchema): Widget {
  if (s.anyOf) {
    const nonNull = s.anyOf.filter((x) => !(typesOf(x).length === 1 && typesOf(x)[0] === "null"));
    const nullable = nonNull.length < s.anyOf.length;
    if (nonNull.length === 1 && nonNull[0]) {
      const inner = nonNull[0];
      if (typesOf(inner).includes("object") && inner.properties)
        return { kind: "nullable-object", nullable, inner };
      const w = widgetFor(inner);
      return { ...w, nullable: nullable || w.nullable };
    }
    return { kind: "json", nullable, inner: s };
  }
  const types = typesOf(s);
  const nullable = types.includes("null");
  const t = types.filter((x) => x !== "null");
  if (s.enum) return { kind: "enum", nullable: nullable || s.enum.includes(null), inner: s };
  if (t.includes("boolean")) return { kind: "boolean", nullable, inner: s };
  if (t.length === 1) {
    const only = t[0];
    if (only === "integer") return { kind: "integer", nullable, inner: s };
    if (only === "number") return { kind: "number", nullable, inner: s };
    if (only === "string") return { kind: "string", nullable, inner: s };
    if (only === "array") {
      if (s.prefixItems?.length) return { kind: "tuple", nullable, inner: s };
      const it = s.items ? typesOf(s.items) : [];
      if (it.length === 1 && ["string", "number", "integer"].includes(it[0] ?? ""))
        return { kind: "list", nullable, inner: s };
      return { kind: "json", nullable, inner: s };
    }
    if (only === "object") {
      const ap = s.additionalProperties;
      if (isRecord(ap) && (ap as JsonSchema).enum) return { kind: "dict-enum", nullable, inner: s };
      return { kind: "json", nullable, inner: s };
    }
  }
  return { kind: "json", nullable, inner: s };
}

export interface PresetLike {
  id: string;
  train: Record<string, unknown>;
  policy: Record<string, unknown>;
  requires_init_from?: boolean;
}

export interface ConfigBase {
  policy: JsonObject;
  train: JsonObject;
}

/** schema defaults <- preset (the API already resolved `per_policy` for this policy type). */
export function presetBase(
  policySchema: JsonSchema,
  trainSchema: JsonSchema,
  preset: PresetLike | null,
): ConfigBase {
  const policy = schemaDefaults(policySchema);
  const train = schemaDefaults(trainSchema);
  return {
    policy: preset ? deepMerge(policy, preset.policy) : policy,
    train: preset ? deepMerge(train, preset.train) : train,
  };
}

/**
 * Request config: every basic field (spec: "UI sends the full basic set") plus advanced fields
 * that differ from defaults+preset. Server re-applies defaults <- preset <- these values.
 */
export function buildRequestConfig(
  values: ConfigBase,
  base: ConfigBase,
  policySchema: JsonSchema,
  trainSchema: JsonSchema,
): ConfigBase {
  const pick = (vals: JsonObject, baseVals: JsonObject, schema: JsonSchema): JsonObject => {
    const { basic, advanced } = groupFields(schema);
    const out: JsonObject = {};
    for (const f of basic) {
      const v = vals[f.name];
      if (v !== undefined) out[f.name] = v;
    }
    for (const f of advanced) {
      const v = vals[f.name];
      if (v !== undefined && !jsonEqual(v, baseVals[f.name])) out[f.name] = v;
    }
    return out;
  };
  return {
    policy: pick(values.policy, base.policy, policySchema),
    train: pick(values.train, base.train, trainSchema),
  };
}

// ---- validation -------------------------------------------------------------------------------

export interface FieldIssue {
  field: string;
  keyword: string;
  params: Record<string, unknown>;
}

function issueField(e: SchemaError): string {
  const path = e.instancePath.replace(/^\//, "").split("/")[0] ?? "";
  if (path) return path;
  if (e.keyword === "additionalProperties" && isRecord(e.params))
    return String(e.params.additionalProperty ?? "");
  if (e.keyword === "required" && isRecord(e.params)) return String(e.params.missingProperty ?? "");
  return "";
}

const RULE_RE = /^([a-z_][a-z0-9_]*)\s*(<=|<|>=|>|==|!=)\s*([a-z_][a-z0-9_]*|-?\d+(?:\.\d+)?)$/;

/** Evaluate simple `a <op> b` cross-field rules; complex rules are left to the server (422). */
export function checkCrossFieldRules(values: JsonObject, schema: JsonSchema): FieldIssue[] {
  const out: FieldIssue[] = [];
  for (const r of schema["x-hibiscus"]?.cross_field_rules ?? []) {
    const m = RULE_RE.exec(r.rule.trim());
    if (!m) continue;
    const [, a = "", op, b = ""] = m;
    const av = values[a];
    const bv = /^-?\d/.test(b) ? Number(b) : values[b];
    if (typeof av !== "number" || typeof bv !== "number") continue;
    const ok =
      op === "<="
        ? av <= bv
        : op === "<"
          ? av < bv
          : op === ">="
            ? av >= bv
            : op === ">"
              ? av > bv
              : op === "=="
                ? av === bv
                : av !== bv;
    if (!ok) out.push({ field: a, keyword: "cross_field", params: { rule: r.rule, other: b } });
  }
  return out;
}

export function validateValues(values: JsonObject, schema: JsonSchema): FieldIssue[] {
  const issues: FieldIssue[] = [];
  for (const e of validate(schema as Record<string, unknown>, values)) {
    // anyOf branches produce noise; report one issue per field+keyword.
    const field = issueField(e);
    if (!issues.some((i) => i.field === field && i.keyword === e.keyword)) {
      issues.push({ field, keyword: e.keyword, params: e.params });
    }
  }
  return [...issues, ...checkCrossFieldRules(values, schema)];
}

/** Group issues by field (first issue wins) for rendering next to inputs. */
export function issuesByField(issues: readonly FieldIssue[]): Map<string, FieldIssue> {
  const m = new Map<string, FieldIssue>();
  for (const i of issues) if (!m.has(i.field)) m.set(i.field, i);
  return m;
}

export function humanize(name: string): string {
  const s = name.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ---- log_freq follows short step counts (QC-e2e-11) -------------------------------------------

const MIN_LOG_FREQ = 10;

/** log_freq that yields at least ~10 metric points for `steps` (never above the preset's value). */
export function autoLogFreq(steps: number, baseLogFreq: number): number {
  if (baseLogFreq * 10 <= steps) return baseLogFreq;
  return Math.max(MIN_LOG_FREQ, Math.min(baseLogFreq, Math.floor(steps / 10)));
}

/**
 * When the user lowers `steps` (e.g. a 200-step smoke run with the preset's log_freq 200, which
 * gives one metric point), lower `log_freq` with it, unless the user set log_freq themselves.
 */
export function followLogFreq(prev: JsonObject, next: JsonObject, base: JsonObject): JsonObject {
  const steps = next.steps;
  const baseLf = base.log_freq;
  if (typeof steps !== "number" || typeof baseLf !== "number" || baseLf <= 0) return next;
  if (steps === prev.steps) return next;
  const current = next.log_freq;
  const prevAuto = typeof prev.steps === "number" ? autoLogFreq(prev.steps, baseLf) : baseLf;
  if (current !== undefined && current !== baseLf && current !== prevAuto) return next; // user-set
  const lf = autoLogFreq(steps, baseLf);
  return lf === current ? next : { ...next, log_freq: lf };
}
