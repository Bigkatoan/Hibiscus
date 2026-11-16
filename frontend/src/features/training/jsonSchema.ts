/**
 * Interpreting JSON Schema (2020-12 subset) validator for the policy/train schemas.
 *
 * Why not Ajv: Ajv compiles every schema to JavaScript with `new Function`, and the deployed SPA
 * runs under `script-src 'self'` (no 'unsafe-eval', deploy/caddy/Caddyfile). The schemas come from
 * the API at runtime (generated from the installed LeRobot), so build-time Ajv standalone code
 * cannot cover them. This walker never generates code (QC-e2e-04).
 *
 * Supported keywords: type, enum, const, minimum, maximum, exclusiveMinimum, exclusiveMaximum,
 * multipleOf, minLength, maxLength, pattern, items, prefixItems, minItems, maxItems, uniqueItems,
 * properties, additionalProperties, required, minProperties, maxProperties, anyOf, oneOf, allOf,
 * not. Unknown keywords (annotations, x-hibiscus-*, format) are ignored, as with Ajv `strict:false`
 * and `validateFormats:false`. Errors use Ajv's shape (`instancePath`, `keyword`, `params`).
 */

export interface SchemaError {
  instancePath: string;
  keyword: string;
  params: Record<string, unknown>;
}

type Schema = boolean | Record<string, unknown>;

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function matchesType(v: unknown, t: string): boolean {
  switch (t) {
    case "null":
      return v === null;
    case "boolean":
      return typeof v === "boolean";
    case "integer":
      return typeof v === "number" && Number.isInteger(v);
    case "number":
      return typeof v === "number" && Number.isFinite(v);
    case "string":
      return typeof v === "string";
    case "array":
      return Array.isArray(v);
    case "object":
      return isObj(v);
    default:
      return true;
  }
}

/** Structural equality for enum/const/uniqueItems (key order independent). */
export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a === "number" && typeof b === "number") return a === b;
  if (Array.isArray(a) && Array.isArray(b))
    return a.length === b.length && a.every((x, i) => deepEqual(x, b[i]));
  if (isObj(a) && isObj(b)) {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    return ka.length === kb.length && ka.every((k) => k in b && deepEqual(a[k], b[k]));
  }
  return false;
}

const patternCache = new Map<string, RegExp | null>();
function regex(p: string): RegExp | null {
  if (!patternCache.has(p)) {
    let re: RegExp | null = null;
    try {
      re = new RegExp(p, "u");
    } catch {
      re = null; // invalid pattern: ignore rather than crash the wizard
    }
    patternCache.set(p, re);
  }
  return patternCache.get(p) ?? null;
}

function esc(key: string): string {
  return key.replace(/~/g, "~0").replace(/\//g, "~1");
}

function walk(schema: Schema, v: unknown, path: string, errors: SchemaError[]): void {
  if (schema === true) return;
  if (schema === false) {
    errors.push({ instancePath: path, keyword: "false schema", params: {} });
    return;
  }
  const s = schema;
  const err = (keyword: string, params: Record<string, unknown> = {}) => {
    errors.push({ instancePath: path, keyword, params });
  };

  if (s.type !== undefined) {
    const types = Array.isArray(s.type)
      ? (s.type as unknown[]).map((x) => (typeof x === "string" ? x : ""))
      : [typeof s.type === "string" ? s.type : ""];
    if (!types.some((t) => matchesType(v, t))) {
      err("type", { type: types.join(",") });
      return; // further keywords would only add noise
    }
  }
  if (Array.isArray(s.enum) && !s.enum.some((e) => deepEqual(e, v))) err("enum", { allowedValues: s.enum });
  if ("const" in s && !deepEqual(s.const, v)) err("const", { allowedValue: s.const });

  if (typeof v === "number") {
    const cmp = (kw: string, bad: (lim: number) => boolean, comparison: string) => {
      const lim = s[kw];
      if (typeof lim === "number" && bad(lim)) err(kw, { comparison, limit: lim });
    };
    cmp("minimum", (l) => v < l, ">=");
    cmp("maximum", (l) => v > l, "<=");
    cmp("exclusiveMinimum", (l) => v <= l, ">");
    cmp("exclusiveMaximum", (l) => v >= l, "<");
    if (typeof s.multipleOf === "number" && s.multipleOf > 0) {
      const q = v / s.multipleOf;
      if (Math.abs(q - Math.round(q)) > 1e-9) err("multipleOf", { multipleOf: s.multipleOf });
    }
  }

  if (typeof v === "string") {
    const len = Array.from(v).length; // code points, as JSON Schema requires
    if (typeof s.minLength === "number" && len < s.minLength) err("minLength", { limit: s.minLength });
    if (typeof s.maxLength === "number" && len > s.maxLength) err("maxLength", { limit: s.maxLength });
    if (typeof s.pattern === "string") {
      const re = regex(s.pattern);
      if (re && !re.test(v)) err("pattern", { pattern: s.pattern });
    }
  }

  if (Array.isArray(v)) {
    if (typeof s.minItems === "number" && v.length < s.minItems) err("minItems", { limit: s.minItems });
    if (typeof s.maxItems === "number" && v.length > s.maxItems) err("maxItems", { limit: s.maxItems });
    const prefix = Array.isArray(s.prefixItems) ? (s.prefixItems as Schema[]) : [];
    prefix.forEach((ps, i) => {
      if (i < v.length) walk(ps, v[i], `${path}/${i}`, errors);
    });
    if (s.items !== undefined && (typeof s.items === "boolean" || isObj(s.items))) {
      for (let i = prefix.length; i < v.length; i++) walk(s.items, v[i], `${path}/${i}`, errors);
    }
    if (s.uniqueItems === true) {
      outer: for (let i = 0; i < v.length; i++)
        for (let j = i + 1; j < v.length; j++)
          if (deepEqual(v[i], v[j])) {
            err("uniqueItems", { i, j });
            break outer;
          }
    }
  }

  if (isObj(v)) {
    const props = isObj(s.properties) ? (s.properties as Record<string, Schema>) : {};
    if (Array.isArray(s.required))
      for (const r of s.required as string[]) if (!(r in v)) err("required", { missingProperty: r });
    const n = Object.keys(v).length;
    if (typeof s.minProperties === "number" && n < s.minProperties)
      err("minProperties", { limit: s.minProperties });
    if (typeof s.maxProperties === "number" && n > s.maxProperties)
      err("maxProperties", { limit: s.maxProperties });
    for (const [k, val] of Object.entries(v)) {
      const ps = props[k];
      if (ps !== undefined) walk(ps, val, `${path}/${esc(k)}`, errors);
      else if (s.additionalProperties === false) err("additionalProperties", { additionalProperty: k });
      else if (isObj(s.additionalProperties)) walk(s.additionalProperties, val, `${path}/${esc(k)}`, errors);
    }
  }

  if (Array.isArray(s.allOf)) for (const sub of s.allOf as Schema[]) walk(sub, v, path, errors);
  if (Array.isArray(s.anyOf)) {
    const branchErrors: SchemaError[] = [];
    const ok = (s.anyOf as Schema[]).some((sub) => {
      const e: SchemaError[] = [];
      walk(sub, v, path, e);
      branchErrors.push(...e);
      return e.length === 0;
    });
    if (!ok) {
      errors.push(...branchErrors);
      err("anyOf");
    }
  }
  if (Array.isArray(s.oneOf)) {
    const passing = (s.oneOf as Schema[]).filter((sub) => validate(sub, v).length === 0).length;
    if (passing !== 1) err("oneOf", { passingSchemas: passing });
  }
  if (s.not !== undefined && (typeof s.not === "boolean" || isObj(s.not))) {
    if (validate(s.not, v).length === 0) err("not");
  }
}

/** Validate `value` against `schema`; returns all errors (Ajv `allErrors: true` semantics). */
export function validate(schema: Schema, value: unknown): SchemaError[] {
  const errors: SchemaError[] = [];
  walk(schema, value, "", errors);
  return errors;
}
