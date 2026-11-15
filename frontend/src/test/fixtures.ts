/**
 * Typed fixtures for UI tests and the MSW mock server. Every fixture is typed with the generated
 * `components["schemas"]` AND validated at runtime against api/openapi.yaml by
 * `src/test/contract.test.ts`, so the mocks cannot drift from the contract.
 */
import type { Schemas } from "@/api/client";
import actSchema from "../../../api/policy-schemas/act.json";
import presetsDoc from "../../../api/policy-schemas/presets.json";
import trainSchema from "../../../api/policy-schemas/train.json";

type S = Schemas;

export const T0 = "2026-11-15T09:30:00Z";
export const IDS = {
  user: "11111111-1111-4111-8111-111111111111",
  user2: "11111111-1111-4111-8111-222222222222",
  ws: "22222222-2222-4222-8222-222222222222",
  ws2: "22222222-2222-4222-8222-333333333333",
  dataset: "33333333-3333-4333-8333-333333333333",
  version: "44444444-4444-4444-8444-444444444444",
  version2: "44444444-4444-4444-8444-555555555555",
  job: "55555555-5555-4555-8555-555555555555",
  run: "66666666-6666-4666-8666-666666666666",
  run2: "66666666-6666-4666-8666-777777777777",
  model: "77777777-7777-4777-8777-777777777777",
  checkpoint: "88888888-8888-4888-8888-888888888888",
  session: "99999999-9999-4999-8999-999999999999",
  session2: "99999999-9999-4999-8999-aaaaaaaaaaaa",
  token: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  invite: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  upload: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  notification: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  channel: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
} as const;

export const SHA = "a".repeat(64);
export const JOINTS = [
  "shoulder_pan.pos",
  "shoulder_lift.pos",
  "elbow_flex.pos",
  "wrist_flex.pos",
  "wrist_roll.pos",
  "gripper.pos",
];

export const user: S["User"] = {
  id: IDS.user,
  email: "an@example.com",
  display_name: "An Nguyen",
  locale: "en",
  email_verified: true,
  mfa_enabled: true,
  is_platform_admin: true,
  created_at: T0,
};

export const membership: S["Membership"] = {
  workspace_id: IDS.ws,
  workspace_slug: "robot-lab",
  workspace_name: "Robot Lab",
  role: "owner",
};

export const membership2: S["Membership"] = {
  workspace_id: IDS.ws2,
  workspace_slug: "side-project",
  workspace_name: "Side Project",
  role: "viewer",
};

export const me: S["Me"] = {
  user,
  memberships: [membership, membership2],
  auth_method: "session",
  session_id: IDS.session,
  mfa_verified: true,
  mfa_enrollment_required: false,
  token: null,
};

export const authConfig: S["AuthConfig"] = {
  turnstile_site_key: null,
  email_delivery_enabled: true,
  password_min_length: 12,
  supported_locales: ["vi", "en"],
};

export const workspace: S["Workspace"] = {
  id: IDS.ws,
  slug: "robot-lab",
  name: "Robot Lab",
  my_role: "owner",
  member_count: 2,
  settings: {
    default_heldout_fraction: 0.1,
    default_gpu: "auto",
    notify_on: ["run.succeeded", "run.failed"],
  },
  created_at: T0,
};

export const workspace2: S["Workspace"] = {
  id: IDS.ws2,
  slug: "side-project",
  name: "Side Project",
  my_role: "viewer",
  member_count: 1,
  created_at: T0,
};

export const members: S["Member"][] = [
  {
    user: { id: IDS.user, display_name: "An Nguyen" },
    email: "an@example.com",
    role: "owner",
    mfa_enabled: true,
    joined_at: T0,
  },
  {
    user: { id: IDS.user2, display_name: "Binh Tran" },
    email: "binh@example.com",
    role: "member",
    mfa_enabled: false,
    joined_at: T0,
  },
];

export const invite: S["Invite"] = {
  id: IDS.invite,
  email: "chi@example.com",
  role: "member",
  invited_by: { id: IDS.user, display_name: "An Nguyen" },
  status: "pending",
  expires_at: "2026-11-18T09:30:00Z",
  created_at: T0,
};

export const invitePreview: S["InvitePreview"] = {
  workspace_name: "Robot Lab",
  email: "chi@example.com",
  role: "member",
  invited_by: "An Nguyen",
  expires_at: "2026-11-18T09:30:00Z",
  account_exists: false,
};

export const sessions: S["SessionInfo"][] = [
  {
    id: IDS.session,
    created_at: T0,
    last_used_at: T0,
    expires_at: "2026-12-15T09:30:00Z",
    ip: "203.0.113.5",
    user_agent: "Mozilla/5.0 Firefox/140.0",
    current: true,
    mfa_verified: true,
  },
  {
    id: IDS.session2,
    created_at: T0,
    last_used_at: T0,
    expires_at: "2026-12-15T09:30:00Z",
    ip: "198.51.100.7",
    user_agent: "Mozilla/5.0 Chrome/150.0",
    current: false,
    mfa_verified: true,
  },
];

export const apiToken: S["ApiToken"] = {
  id: IDS.token,
  name: "collect-pc",
  prefix: "ab12cd34",
  workspace_id: IDS.ws,
  scopes: ["datasets:write", "runs:read"],
  created_at: T0,
  expires_at: "2027-02-13T09:30:00Z",
  last_used_at: null,
  last_used_ip: null,
  revoked_at: null,
};

export const job: S["Job"] = {
  id: IDS.job,
  workspace_id: IDS.ws,
  kind: "validate_dataset",
  status: "queued",
  progress: 0,
  stage: null,
  error_code: null,
  error_message: null,
  result: null,
  run_id: null,
  dataset_version_id: IDS.version,
  model_id: null,
  created_at: T0,
  started_at: null,
  finished_at: null,
};

export const versionSummary: S["DatasetVersionSummary"] = {
  id: IDS.version,
  dataset_id: IDS.dataset,
  version: 1,
  status: "ready",
  source: "upload",
  total_episodes: 20,
  total_frames: 11277,
  fps: 30,
  size_bytes: 512 * 1024 * 1024,
  created_at: T0,
};

export const dataset: S["Dataset"] = {
  id: IDS.dataset,
  workspace_id: IDS.ws,
  name: "so101 pick and place",
  slug: "so101-pick-and-place",
  description: "Wrist cam, 20 episodes",
  created_by: { id: IDS.user, display_name: "An Nguyen" },
  version_count: 1,
  latest_version: versionSummary,
  created_at: T0,
  updated_at: T0,
};

export const datasetVersion: S["DatasetVersion"] = {
  ...versionSummary,
  content_hash: SHA,
  source_ref: null,
  merged_from: null,
  codebase_version: "v3.0",
  converted_from: null,
  robot_type: "so_follower",
  camera_keys: ["observation.images.wrist_cam"],
  features: {
    action: { dtype: "float32", shape: [6], names: JOINTS },
    "observation.state": { dtype: "float32", shape: [6], names: JOINTS },
    "observation.images.wrist_cam": {
      dtype: "video",
      shape: [360, 640, 3],
      names: ["height", "width", "channels"],
    },
  },
  state_dim: 6,
  action_dim: 6,
  joint_names: JOINTS,
  tasks: ["Pick the cube and place it in the box"],
  validation_summary: { result: "passed_with_warnings", errors: 0, warnings: 1 },
  error_code: null,
  ready_at: T0,
};

export const validationReport: S["ValidationReport"] = {
  dataset_version_id: IDS.version,
  job_id: IDS.job,
  validator_version: "1",
  lerobot_version: "0.7.1",
  summary: { result: "passed_with_warnings", errors: 0, warnings: 1 },
  steps: [
    { id: "checksum", status: "passed", started_at: T0, finished_at: T0, progress: 1, issues: [] },
    { id: "unpack", status: "passed", started_at: T0, finished_at: T0, progress: 1, issues: [] },
    { id: "structure", status: "passed", started_at: T0, finished_at: T0, progress: 1, issues: [] },
    { id: "schema", status: "passed", started_at: T0, finished_at: T0, progress: 1, issues: [] },
    {
      id: "decode",
      status: "warning",
      started_at: T0,
      finished_at: T0,
      progress: 1,
      issues: [
        {
          code: "timestamp_irregular",
          severity: "warning",
          message: "Episode 3 has irregular timestamps",
          params: { max_gap_s: 0.07 },
          episode_index: 3,
          path: null,
          feature: null,
        },
      ],
    },
    { id: "timestamps", status: "passed", started_at: T0, finished_at: T0, progress: 1, issues: [] },
    { id: "stats", status: "passed", started_at: T0, finished_at: T0, progress: 1, issues: [] },
  ],
  recomputed_stats_max_rel_diff: { action: 0.001 },
};

export const preview: S["DatasetPreview"] = {
  dataset_version_id: IDS.version,
  fps: 30,
  camera_keys: ["observation.images.wrist_cam"],
  episodes: Array.from({ length: 3 }, (_, i) => ({
    index: i,
    length: 560 + i,
    duration_s: (560 + i) / 30,
    tasks: ["Pick the cube and place it in the box"],
    thumbnails: {
      "observation.images.wrist_cam": `previews/observation.images.wrist_cam/episode_00000${i}.jpg`,
    },
    has_issues: i === 2,
  })),
  length_histogram: { bin_edges_s: [10, 15, 20, 25], counts: [2, 15, 3] },
};

export const episode: S["EpisodeDetail"] = {
  index: 0,
  length: 5,
  fps: 30,
  timestamps: [0, 0.0333, 0.0667, 0.1, 0.1333],
  series: [
    ...JOINTS.map((name, dim) => ({
      feature: "observation.state",
      dim,
      name,
      values: [0, 1, 2, null, 4].map((v) => (v === null ? null : v + dim)),
    })),
    ...JOINTS.map((name, dim) => ({ feature: "action", dim, name, values: [0, 1, 2, 3, 4] })),
  ],
  videos: [
    {
      camera_key: "observation.images.wrist_cam",
      media_path: "videos/observation.images.wrist_cam/chunk-000/file-000.mp4",
      from_timestamp_s: 0,
      to_timestamp_s: 18.7,
      codec: "av1",
      width: 640,
      height: 360,
      browser_playable_hint: false,
      preview_media_path: "previews/observation.images.wrist_cam/episode_000000.mp4",
      thumbnail_media_path: "previews/observation.images.wrist_cam/episode_000000.jpg",
    },
  ],
};

export const uploadSession: S["UploadSession"] = {
  id: IDS.upload,
  workspace_id: IDS.ws,
  dataset_id: null,
  new_dataset_name: "so101",
  filename: "Picknplace.rar",
  size: 10,
  sha256: SHA,
  archive_format: "rar",
  part_size: 5 * 1024 * 1024,
  part_count: 1,
  parts: [],
  bytes_received: 0,
  status: "active",
  error_code: null,
  expires_at: "2026-11-22T09:30:00Z",
  created_at: T0,
  completed_at: null,
  dataset_version_id: null,
};

export const policySummaries: S["PolicySummary"][] = [
  {
    type: "act",
    display_name: "ACT",
    trainable: true,
    onnx: "full",
    onnx_reason_key: null,
    requires_peft: false,
    requires_reward: false,
    requires_language: false,
    gpu_support: { "RTX 3060": "supported", "Tesla P40": "supported" },
    schema_etag: "act-1",
    experimental: false,
  },
  {
    type: "tdmpc",
    display_name: "TD-MPC",
    trainable: true,
    onnx: "none",
    onnx_reason_key: "policy.onnx_reason.tdmpc",
    requires_peft: false,
    requires_reward: true,
    requires_language: false,
    gpu_support: { "RTX 3060": "supported", "Tesla P40": "supported" },
    schema_etag: "tdmpc-1",
    experimental: false,
  },
  {
    type: "pi0",
    display_name: "Pi0",
    trainable: true,
    onnx: "none",
    onnx_reason_key: "policy.onnx_reason.vlm",
    requires_peft: true,
    requires_reward: false,
    requires_language: true,
    gpu_support: { "RTX 3060": "unsupported", "Tesla P40": "limited" },
    schema_etag: "pi0-1",
    experimental: true,
  },
];

interface RawPreset {
  id: "quick" | "standard" | "finetune";
  label_key: string;
  requires_init_from: boolean;
  train: Record<string, unknown>;
  policy: Record<string, unknown>;
}

export const actPolicy: S["PolicyDetail"] = {
  ...policySummaries[0]!,
  policy_schema: actSchema as Record<string, unknown>,
  train_schema: trainSchema as Record<string, unknown>,
  presets: (presetsDoc.presets as RawPreset[]).map((p) => ({
    id: p.id,
    label_key: p.label_key,
    requires_init_from: p.requires_init_from,
    train: p.train,
    policy: p.policy,
  })),
};

export const estimate: S["ResourceEstimate"] = {
  source: "measured",
  gpu_id: "cuda0",
  peak_vram_mb: 1843,
  sec_per_step: 0.11,
  total_duration_s: 1100,
  measured_at: T0,
};

export const run: S["Run"] = {
  id: IDS.run,
  workspace_id: IDS.ws,
  number: 7,
  name: "act-picknplace",
  status: "running",
  status_changed_at: T0,
  desired_state: "run",
  error_code: null,
  error_message: null,
  policy_type: "act",
  preset: "quick",
  dataset_version_id: IDS.version,
  dataset: { id: IDS.dataset, name: "so101 pick and place", version: 1 },
  config: { policy: { chunk_size: 100 }, train: { steps: 10000, batch_size: 8 } },
  heldout_episodes: [3, 11],
  seed: 1000,
  progress: {
    current_step: 2500,
    total_steps: 10000,
    steps_per_s: 9.1,
    eta_s: 824,
    next_checkpoint_step: 5000,
    last_checkpoint_step: null,
  },
  latest_metrics: { loss: 0.52, grad_norm: 12.4, lr: 0.00001 },
  gpu_id: "cuda0",
  requested_gpu: "auto",
  mixed_precision_requested: "bf16",
  mixed_precision_effective: "bf16",
  priority: 0,
  queue_position: null,
  attempt: 1,
  infra_retries_used: 0,
  estimate,
  parent_run_id: null,
  init_from: null,
  export: { onnx: true, onnx_fp16: false, eval: true },
  model_id: null,
  gpu_seconds: 275,
  created_by: { id: IDS.user, display_name: "An Nguyen" },
  created_at: T0,
  updated_at: T0,
  queued_at: T0,
  started_at: T0,
  finished_at: null,
  allowed_actions: ["cancel", "pause", "clone", "edit"],
};

export const run2: S["Run"] = {
  ...run,
  id: IDS.run2,
  number: 6,
  name: "act-baseline",
  status: "succeeded",
  progress: { ...run.progress, current_step: 10000, eta_s: null, last_checkpoint_step: 10000 },
  model_id: IDS.model,
  finished_at: T0,
  allowed_actions: ["clone", "export", "eval"],
};

export const metricSeries: S["MetricSeriesSet"] = {
  run_id: IDS.run,
  series: [
    {
      key: "loss",
      steps: [200, 400, 600],
      values: [2.1, 1.2, 0.8],
      has_nonfinite: false,
      downsampled: false,
    },
    {
      key: "grad_norm",
      steps: [200, 400, 600],
      values: [40, 22, null],
      has_nonfinite: true,
      downsampled: false,
    },
    {
      key: "lr",
      steps: [200, 400, 600],
      values: [1e-5, 1e-5, 1e-5],
      has_nonfinite: false,
      downsampled: false,
    },
  ],
};

export const gpuSample: S["GpuSample"] = {
  gpu_id: "cuda0",
  ts: T0,
  util_pct: 87,
  mem_used_mb: 2100,
  mem_total_mb: 12288,
  temperature_c: 64,
  power_w: 141,
};

export const checkpoint: S["Checkpoint"] = {
  id: IDS.checkpoint,
  run_id: IDS.run2,
  step: 10000,
  size_bytes: 206 * 1024 * 1024,
  is_last: true,
  has_training_state: true,
  model_id: IDS.model,
  eval_summary: null,
  created_at: T0,
};

export const model: S["Model"] = {
  id: IDS.model,
  workspace_id: IDS.ws,
  name: "act-picknplace",
  policy_type: "act",
  run_id: IDS.run2,
  run_number: 6,
  checkpoint_id: IDS.checkpoint,
  step: 10000,
  status: "ready",
  error_message: null,
  verified: true,
  verification: {
    load_ok: true,
    parity_ok: true,
    manifest_ok: true,
    parity: { max_abs_diff: 0.00002, atol: 0.0001, rtol: 0.001, n_samples: 32 },
    checked_at: T0,
    details: null,
  },
  onnx_status: "passed",
  onnx_detail: null,
  bundle_size_bytes: 210 * 1024 * 1024,
  bundle_sha256: SHA,
  dataset: { id: IDS.dataset, name: "so101 pick and place", version: 1 },
  eval_summary: { action_mae: 0.031, action_mse: 0.002 },
  hub_repo_id: null,
  hub_pushed_at: null,
  created_by: { id: IDS.user, display_name: "An Nguyen" },
  created_at: T0,
};

export const bundleManifest: S["BundleManifest"] = {
  schema_version: "1",
  bundle_name: "act-picknplace-r6-step10000",
  files: [
    { path: "pretrained_model/model.safetensors", size: 206 * 1024 * 1024, sha256: SHA },
    { path: "onnx/model.onnx", size: 205 * 1024 * 1024, sha256: SHA },
    { path: "MODEL_CARD.md", size: 4096, sha256: SHA },
  ],
};

export const gpus: S["GpuNode"][] = [
  {
    id: "cuda0",
    name: "NVIDIA GeForce RTX 3060",
    total_vram_mb: 12288,
    compute_capability: "8.6",
    supports_bf16: true,
    supports_fast_fp16: true,
    status: "online",
    last_heartbeat_at: T0,
    current_run: {
      id: IDS.run,
      name: "act-picknplace",
      workspace_id: IDS.ws,
      step: 2500,
      total_steps: 10000,
    },
    telemetry: gpuSample,
  },
  {
    id: "cuda1",
    name: "Tesla P40",
    total_vram_mb: 24576,
    compute_capability: "6.1",
    supports_bf16: false,
    supports_fast_fp16: false,
    status: "online",
    last_heartbeat_at: T0,
    current_run: null,
    telemetry: null,
  },
];

export const preflightOk: S["PreflightReport"] = {
  ok: true,
  checks: [
    { id: "dataset_ready", severity: "info", code: "ok", message: "Dataset is ready", params: {} },
    {
      id: "mixed_precision",
      severity: "warning",
      code: "mixed_precision_forced_no",
      message: "P40 has no bf16",
      params: { gpu: "cuda1" },
    },
  ],
  resolved: {
    gpu_id: "cuda0",
    mixed_precision: "bf16",
    config: { policy: { chunk_size: 100 }, train: { steps: 10000 } },
    heldout_episodes: [3, 11],
    train_episodes: [0, 1, 2],
    lerobot_args: ["--policy.type=act", "--steps=10000"],
  },
  estimate,
};

export const adminUser: S["AdminUser"] = {
  ...user,
  is_active: true,
  locked_until: null,
  last_login_at: T0,
  workspaces: [membership],
};

export const auditEvent: S["AuditEvent"] = {
  id: 1,
  created_at: T0,
  workspace_id: IDS.ws,
  actor: { id: IDS.user, display_name: "An Nguyen" },
  actor_token_id: null,
  action: "auth.login",
  target_type: "user",
  target_id: IDS.user,
  outcome: "success",
  ip: "203.0.113.5",
  user_agent: "Firefox",
  request_id: "req-1",
  details: {},
};

export const quotaLimits: S["QuotaLimits"] = {
  max_concurrent_runs: 1,
  max_queued_runs: 10,
  gpu_hours_per_month: 200,
  storage_bytes: 200 * 1024 ** 3,
  max_upload_bytes: 50 * 1024 ** 3,
};

export const quota: S["Quota"] = { ...quotaLimits, id: IDS.job, workspace_id: IDS.ws, user_id: null };

export const usage: S["WorkspaceUsage"] = {
  workspace: {
    limits: quotaLimits,
    storage_bytes_used: 3 * 1024 ** 3,
    gpu_hours_this_month: 12.5,
    active_runs: 1,
    queued_runs: 0,
  },
  me: {
    limits: quotaLimits,
    gpu_hours_this_month: 10,
    active_runs: 1,
    queued_runs: 0,
    fair_share_gpu_hours_7d: 4,
  },
};

export const system: S["SystemStatus"] = {
  hibiscus_version: "0.1.0",
  lerobot_version: "0.7.1",
  api_version: "0.1.0",
  queue_depth: 0,
  gpus,
  storage: { buckets: { "hibiscus-datasets": 3 * 1024 ** 3 }, disk_free_bytes: 395 * 1024 ** 3 },
  email: { provider: "cloudflare", enabled: true },
};

export const notification: S["Notification"] = {
  id: IDS.notification,
  workspace_id: IDS.ws,
  kind: "run.succeeded",
  params: { run_name: "act-baseline", run_number: 6 },
  link: `/runs/${IDS.run2}`,
  read: false,
  created_at: T0,
};

export const channel: S["NotificationChannel"] = {
  id: IDS.channel,
  kind: "discord",
  events: ["run.failed"],
  enabled: true,
  target_hint: "discord.com/…/abcd",
  created_at: T0,
};

export function problem(
  status: number,
  code: S["ErrorCode"],
  extra: Partial<S["Problem"]> = {},
): S["Problem"] {
  return {
    type: `https://hibiscus.dev/problems/${code}`,
    title: code,
    status,
    code,
    request_id: "req-test",
    ...extra,
  };
}
