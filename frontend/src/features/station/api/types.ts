/**
 * Hibiscus Station API shapes (docs/spec/station.md §5.3–§5.4), generated from the FastAPI contract
 * `station/openapi.json` into `./schema.d.ts` (`pnpm gen:station-api`; CI runs
 * `pnpm check:station-api`). This file only gives the generated schemas their short names; never
 * hand-write a wire shape here: change `station/hibiscus_station/api/schemas.py` and regenerate.
 */
import type { components } from "./schema";

type S = components["schemas"];

export type Status = S["Status"];
export type StationState = Status["state"];
export type Phase = NonNullable<Status["sub"]>;
export type Arm = S["Hottest"]["arm"];
export type Level = S["Health"]["level"];
export type AlertLevel = S["Alert"]["level"];
export type Problem = S["Problem"];
export type CameraStatus = S["CameraStatus"];
export type Session = S["Session"];
export type SessionEnd = S["SessionEnd"];
export type Alert = S["Alert"];

/** Persisted models: `*-Output` is what the API returns (all fields set), `*-Input` what it accepts. */
export type CameraConfig = S["CameraProfile-Output"];
export type CameraConfigInput = S["CameraProfile-Input"];
export type RobotProfile = S["RobotProfile-Output"];
export type RobotProfileInput = S["RobotProfile-Input"];
export type Thresholds = S["Thresholds-Output"];
export type Settings = S["Settings-Output"];
export type SettingsInput = S["Settings-Input"];
export type Port = S["Port"];
export type DetectResponse = S["DetectResponse"];
export type DiscoveredCamera = S["DiscoveredCamera"];
export type ProbeResult = S["ProbeResult"];
export type CalibrationFile = S["CalibrationFile"];
export type CalibrationView = S["CalibrationView"];
export type CalibrationMotor = S["CalibrationMotor"];
export type CalibrationStepResponse = S["CalibrationStepResponse"];

export type RecordRequest = S["RecordRequest"];
export type RunRequest = S["RunRequest"];
export type ControlAction = S["ControlRequest"]["action"];

export type JobProgress = S["JobProgress"];
export type JobResult = S["JobResult"];
export type Job = S["Job"];

export type CompatCheck = S["CompatCheck"];
export type CompatReport = S["CompatReport"];
export type ModelEntry = S["ModelEntry"];
export type Models = S["Models"];
export type LoadedModel = S["LoadedModel"];

export type LocalDataset = S["LocalDataset"];
export type UploadRecord = S["UploadRecord"];
export type EpisodeSummary = S["EpisodeSummary"];
export type LocalDatasetDetail = S["LocalDatasetDetail"];
export type TelemetrySeries = S["TelemetrySeries"];
export type SessionSummary = S["SessionSummary"];

export type ServerLink = S["ServerLinkView"];
export type ServerDataset = S["ServerDataset"];
export type ServerModel = S["ServerModel"];
export type ServerRun = S["ServerRun"];
export type ServerRuns = S["ServerRuns"];

// ------------------------------------------------------------------ control WebSocket (§5.3)
export type LoopStats = S["LoopStats"];
export type JointsMsg = S["JointsMsg"];
export type MotorSample = S["MotorSample"];
export type MotorLimits = S["MotorLimits"];
export type TelemetryMsg = S["TelemetryMsg"];
export type AlertMsg = S["AlertMsg"];
export type CalibrationMsg = S["CalibrationMsg"];
export type SessionMsg = S["SessionMsg"];
export type ServerMessage = S["ServerMessage"];
export type ClientMessage = S["ClientMessage"];

// ------------------------------------------------------------------ video WebSocket (§5.4)
export type FrameHeader = S["FrameHeader"];
export type VideoSubscribe = S["VideoSubscribe"];
export type CameraErrorMsg = S["CameraErrorMsg"];

export const MOVING_STATES: readonly StationState[] = [
  "teleop",
  "recording",
  "replaying",
  "inferring",
  "calibrating",
];

/** A copy of `obj` without `keys` (for turning a flat WS message into its REST shape). */
export function omit<T extends object, K extends keyof T>(obj: T, ...keys: K[]): Omit<T, K> {
  const drop = new Set<PropertyKey>(keys);
  return Object.fromEntries(Object.entries(obj).filter(([k]) => !drop.has(k))) as Omit<T, K>;
}
