import { PxIcon } from "@/hibiscus/PixelAnim";
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/misc";
import { cn, isRecord } from "@/lib/utils";
import {
  humanize,
  jsonEqual,
  typesOf,
  widgetFor,
  type FieldIssue,
  type FieldSpec,
  type Json,
  type JsonObject,
  type JsonSchema,
} from "./schema";

interface ControlProps {
  id: string;
  describedBy: string | undefined;
  invalid: boolean;
  schema: JsonSchema;
  value: Json | undefined;
  onChange: (v: Json) => void;
}

function NumberControl({
  id,
  describedBy,
  invalid,
  schema,
  value,
  onChange,
  integer,
}: ControlProps & { integer: boolean }) {
  const [text, setText] = useState(value === null || value === undefined ? "" : String(value));
  useEffect(() => {
    const parsed = text.trim() === "" ? null : Number(text);
    if (value === undefined || value === null) {
      if (text !== "") setText("");
    } else if (parsed !== value) setText(String(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <Input
      id={id}
      type="number"
      inputMode={integer ? "numeric" : "decimal"}
      step={integer ? 1 : "any"}
      aria-describedby={describedBy}
      aria-invalid={invalid || undefined}
      {...(schema.minimum !== undefined ? { min: schema.minimum } : {})}
      {...(schema.maximum !== undefined ? { max: schema.maximum } : {})}
      value={text}
      readOnly={schema.const !== undefined}
      onChange={(e) => {
        setText(e.target.value);
        const raw = e.target.value.trim();
        if (raw === "") return;
        const n = Number(raw);
        if (Number.isFinite(n)) onChange(integer ? Math.trunc(n) : n);
      }}
    />
  );
}

function ListControl({ id, describedBy, invalid, schema, value, onChange }: ControlProps) {
  const itemTypes = schema.items ? typesOf(schema.items) : ["string"];
  const numeric = itemTypes.includes("number") || itemTypes.includes("integer");
  const toText = (v: Json | undefined) => (Array.isArray(v) ? v.map(String).join(", ") : "");
  const [text, setText] = useState(toText(value));
  useEffect(() => {
    if (
      toText(value) !==
      text
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean)
        .join(", ")
    )
      setText(toText(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <Input
      id={id}
      aria-describedby={describedBy}
      aria-invalid={invalid || undefined}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        const parts = e.target.value
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean);
        onChange(numeric ? parts.map(Number).filter((n) => Number.isFinite(n)) : parts);
      }}
    />
  );
}

function TupleControl({ id, describedBy, invalid, schema, value, onChange }: ControlProps) {
  const { t } = useTranslation();
  const items = schema.prefixItems ?? [];
  const arr = Array.isArray(value) ? value : [];
  return (
    <div className="flex gap-2" role="group" aria-describedby={describedBy}>
      {items.map((it, i) => (
        <Input
          key={i}
          id={i === 0 ? id : `${id}-${i}`}
          type="number"
          step={typesOf(it).includes("integer") ? 1 : "any"}
          aria-label={t("schema_form.tuple_item", { index: i + 1 })}
          aria-invalid={invalid || undefined}
          className="w-28"
          value={arr[i] === undefined || arr[i] === null ? "" : String(arr[i])}
          onChange={(e) => {
            const next = [...arr];
            while (next.length < items.length) next.push(0);
            const n = Number(e.target.value);
            next[i] = Number.isFinite(n) ? n : 0;
            onChange(next);
          }}
        />
      ))}
    </div>
  );
}

function DictEnumControl({ id, describedBy, schema, value, onChange }: ControlProps) {
  const options =
    (isRecord(schema.additionalProperties) ? (schema.additionalProperties as JsonSchema).enum : []) ?? [];
  const obj = isRecord(value) ? (value as JsonObject) : {};
  const keys = Object.keys(isRecord(schema.default) ? (schema.default as JsonObject) : obj);
  return (
    <div className="grid gap-2 sm:grid-cols-3" role="group" aria-describedby={describedBy} id={id}>
      {keys.map((k) => (
        <label key={k} className="space-y-1 text-xs">
          <span className="font-medium">{k}</span>
          <NativeSelect
            value={String(obj[k] ?? "")}
            onChange={(e) => {
              onChange({ ...obj, [k]: e.target.value });
            }}
          >
            {options.map((o) => (
              <option key={String(o)} value={String(o)}>
                {String(o)}
              </option>
            ))}
          </NativeSelect>
        </label>
      ))}
    </div>
  );
}

function JsonControl({ id, describedBy, invalid, value, onChange }: ControlProps) {
  const { t } = useTranslation();
  const [text, setText] = useState(JSON.stringify(value ?? null));
  const [bad, setBad] = useState(false);
  return (
    <>
      <Textarea
        id={id}
        className="font-mono text-xs"
        rows={2}
        aria-describedby={describedBy}
        aria-invalid={invalid || bad || undefined}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          try {
            onChange(JSON.parse(e.target.value) as Json);
            setBad(false);
          } catch {
            setBad(true);
          }
        }}
      />
      {bad ? <p className="text-xs text-destructive">{t("schema_form.invalid_json")}</p> : null}
    </>
  );
}

function ScalarControl(props: ControlProps & { kind: string }) {
  const { id, describedBy, invalid, schema, value, onChange, kind } = props;
  switch (kind) {
    case "boolean":
      return (
        <Switch
          id={id}
          aria-describedby={describedBy}
          checked={value === true || value === 1}
          onCheckedChange={(c) => {
            onChange(c);
          }}
        />
      );
    case "integer":
    case "number":
      return <NumberControl {...props} integer={kind === "integer"} />;
    case "enum":
      return (
        <NativeSelect
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => {
            const opt = (schema.enum ?? []).find((o) => String(o) === e.target.value);
            onChange(opt ?? e.target.value);
          }}
        >
          {(schema.enum ?? [])
            .filter((o) => o !== null)
            .map((o) => (
              <option key={String(o)} value={String(o)}>
                {String(o)}
              </option>
            ))}
        </NativeSelect>
      );
    case "string":
      return (
        <Input
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          spellCheck={false}
          value={typeof value === "string" ? value : ""}
          {...(schema.pattern ? { pattern: schema.pattern } : {})}
          onChange={(e) => {
            onChange(e.target.value);
          }}
        />
      );
    case "tuple":
      return <TupleControl {...props} />;
    case "list":
      return <ListControl {...props} />;
    case "dict-enum":
      return <DictEnumControl {...props} />;
    default:
      return <JsonControl {...props} />;
  }
}

export interface SchemaFieldProps {
  field: FieldSpec;
  value: Json | undefined;
  baseValue: Json | undefined;
  onChange: (v: Json | undefined) => void;
  issue?: FieldIssue | undefined;
  /** i18n namespace for labels: `policy.act` -> `policy.act.<field>.label` / `.help`. */
  labelPrefix: string;
}

export function SchemaField({ field, value, baseValue, onChange, issue, labelPrefix }: SchemaFieldProps) {
  const { t, i18n } = useTranslation();
  const uid = useId();
  const id = `sf-${uid}`;
  const w = widgetFor(field.schema);
  const labelKey = `${labelPrefix}.${field.name}.label`;
  const helpKey = `${labelPrefix}.${field.name}.help`;
  const label = i18n.exists(labelKey) ? t(labelKey) : humanize(field.name);
  const help = i18n.exists(helpKey) ? t(helpKey) : field.schema.description;
  const modified = !jsonEqual(value, baseValue);
  const isNull = value === null;
  const helpId = `${id}-help`;
  const errId = `${id}-err`;
  const describedBy = [help ? helpId : null, issue ? errId : null].filter(Boolean).join(" ") || undefined;
  const nestedFields =
    w.kind === "nullable-object"
      ? Object.entries(w.inner.properties ?? {}).map(
          ([name, schema]): FieldSpec => ({ name, schema, group: "advanced" }),
        )
      : [];
  return (
    <div
      className={cn("rounded-md border p-3", modified && "border-primary/60 bg-primary/5")}
      data-field={field.name}
    >
      <div className="mb-1.5 flex items-start justify-between gap-2">
        <Label htmlFor={id} className="leading-snug">
          {label}
          {modified ? (
            <span className="ml-2 text-xs font-normal text-primary">{t("schema_form.modified")}</span>
          ) : null}
        </Label>
        {modified ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            aria-label={t("schema_form.reset_field", { field: label })}
            onClick={() => {
              onChange(baseValue);
            }}
          >
            <PxIcon name="undo" />
          </Button>
        ) : null}
      </div>
      {w.nullable && w.kind !== "nullable-object" ? (
        <label className="mb-1.5 flex items-center gap-2 text-xs text-muted-foreground">
          <Checkbox
            checked={isNull}
            onChange={(e) => {
              if (e.target.checked) onChange(null);
              else {
                const empty: Json =
                  w.kind === "boolean" ? false : w.kind === "string" ? "" : w.kind === "list" ? [] : 0;
                const fallback: Json = baseValue ?? empty;
                onChange(fallback);
              }
            }}
          />
          {t("schema_form.none")}
        </label>
      ) : null}
      {w.kind === "nullable-object" ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <Switch
              id={id}
              aria-describedby={describedBy}
              checked={!isNull && value !== undefined}
              onCheckedChange={(c) => {
                onChange(c ? (isRecord(baseValue) ? baseValue : {}) : null);
              }}
            />
            <span>{t("schema_form.enabled")}</span>
          </div>
          {isRecord(value) ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {nestedFields.map((nf) => (
                <SchemaField
                  key={nf.name}
                  field={nf}
                  labelPrefix={`${labelPrefix}.${field.name}`}
                  value={(value as JsonObject)[nf.name]}
                  baseValue={nf.schema.default}
                  onChange={(v) => {
                    const rest = Object.fromEntries(
                      Object.entries(value as JsonObject).filter(([k]) => k !== nf.name),
                    );
                    onChange(v === undefined ? rest : { ...rest, [nf.name]: v });
                  }}
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : isNull ? null : (
        <ScalarControl
          id={id}
          describedBy={describedBy}
          invalid={!!issue}
          kind={w.kind}
          schema={w.inner}
          value={value}
          onChange={onChange}
        />
      )}
      {help ? (
        <p id={helpId} className="mt-1.5 text-xs text-muted-foreground">
          {help}
        </p>
      ) : null}
      {field.cli ? <p className="mt-1 font-mono text-[11px] text-muted-foreground">{field.cli}</p> : null}
      {issue ? (
        <p id={errId} className="mt-1 text-xs font-medium text-destructive">
          {t(`schema_form.error.${issue.keyword}`, {
            ...issue.params,
            defaultValue: t("schema_form.error.generic"),
          })}
        </p>
      ) : null}
    </div>
  );
}

export interface SchemaFormProps {
  fields: FieldSpec[];
  values: JsonObject;
  base: JsonObject;
  onChange: (next: JsonObject) => void;
  issues: Map<string, FieldIssue>;
  labelPrefix: string;
}

/** Renders a list of schema fields (one group: basic or advanced). */
export function SchemaForm({ fields, values, base, onChange, issues, labelPrefix }: SchemaFormProps) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {fields.map((f) => (
        <SchemaField
          key={f.name}
          field={f}
          labelPrefix={labelPrefix}
          value={values[f.name]}
          baseValue={base[f.name]}
          issue={issues.get(f.name)}
          onChange={(v) => {
            const rest = Object.fromEntries(Object.entries(values).filter(([k]) => k !== f.name));
            onChange(v === undefined ? rest : { ...rest, [f.name]: v });
          }}
        />
      ))}
    </div>
  );
}
