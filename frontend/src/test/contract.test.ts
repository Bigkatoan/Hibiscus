/**
 * Contract guard: every fixture served by the mock server must validate against the schema
 * declared for that response in api/openapi.yaml (JSON Schema 2020-12 via Ajv).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import * as f from "./fixtures";

const specPath = resolve(__dirname, "../../../api/openapi.yaml");
const spec = parse(readFileSync(specPath, "utf8")) as Record<string, unknown>;

const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema(spec, "openapi.json");

function validate(schemaName: string, value: unknown): string[] {
  const v = ajv.getSchema(`openapi.json#/components/schemas/${schemaName}`);
  if (!v) throw new Error(`schema ${schemaName} not found`);
  if (v(value)) return [];
  return (v.errors ?? []).map((e) => `${e.instancePath} ${e.message ?? ""}`);
}

const cases: [string, unknown][] = [
  ["Me", f.me],
  ["AuthConfig", f.authConfig],
  ["Workspace", f.workspace],
  ["Workspace", f.workspace2],
  ["Member", f.members[0]],
  ["Member", f.members[1]],
  ["Invite", f.invite],
  ["InvitePreview", f.invitePreview],
  ["SessionInfo", f.sessions[0]],
  ["ApiToken", f.apiToken],
  ["Job", f.job],
  ["Dataset", f.dataset],
  ["DatasetVersion", f.datasetVersion],
  ["ValidationReport", f.validationReport],
  ["DatasetPreview", f.preview],
  ["EpisodeDetail", f.episode],
  ["UploadSession", f.uploadSession],
  ["PolicySummary", f.policySummaries[0]],
  ["PolicySummary", f.policySummaries[2]],
  ["PolicyDetail", f.actPolicy],
  ["Run", f.run],
  ["Run", f.run2],
  ["MetricSeriesSet", f.metricSeries],
  ["GpuSample", f.gpuSample],
  ["Checkpoint", f.checkpoint],
  ["Model", f.model],
  ["BundleManifest", f.bundleManifest],
  ["GpuNode", f.gpus[0]],
  ["GpuNode", f.gpus[1]],
  ["PreflightReport", f.preflightOk],
  ["AdminUser", f.adminUser],
  ["AuditEvent", f.auditEvent],
  ["Quota", f.quota],
  ["WorkspaceUsage", f.usage],
  ["SystemStatus", f.system],
  ["Notification", f.notification],
  ["NotificationChannel", f.channel],
  ["Problem", f.problem(401, "token_expired")],
];

describe("fixtures conform to api/openapi.yaml", () => {
  it.each(cases)("%s", (schema, value) => {
    expect(validate(schema, value)).toEqual([]);
  });

  it("rejects a non-conforming object (validator is live)", () => {
    expect(validate("Run", { ...f.run, status: "exploded" }).length).toBeGreaterThan(0);
  });
});
