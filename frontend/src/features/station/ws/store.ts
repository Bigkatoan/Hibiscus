/**
 * Live Station state fed by the control WebSocket (§5.3): status, joints (+10 s history),
 * motor telemetry (+120 s temperature history), active alerts, calibration progress and jobs.
 * A tiny external store read with useSyncExternalStore; every update replaces the snapshot.
 */
import type {
  AlertMsg,
  Arm,
  CalibrationMsg,
  Job,
  JointsMsg,
  MotorLimits,
  MotorSample,
  ServerMessage,
  Session,
  Status,
} from "../api/types";
import { omit } from "../api/types";

export type ConnState = "connecting" | "open" | "reconnecting" | "closed";

export interface Series {
  t: number[];
  v: (number | null)[];
}

export interface JointHistory {
  t: number[];
  obs: Record<string, (number | null)[]>;
  cmd: Record<string, (number | null)[]>;
  clipped: Record<string, number[]>;
}

export interface StationSnapshot {
  conn: ConnState;
  status: Status | null;
  joints: JointsMsg | null;
  jointHist: JointHistory;
  telemetry: Partial<Record<Arm, Record<string, MotorSample>>>;
  tempHist: Partial<Record<Arm, Record<string, Series>>>;
  limits: Partial<Record<Arm, MotorLimits>>;
  alerts: AlertMsg[];
  calibration: CalibrationMsg | null;
  jobs: Record<string, Job>;
  /** Max temperature per `${arm}.${motor}` since the last `resetPeaks()` (run summary). */
  peaks: Record<string, number>;
  alertCount: number;
  /** The most recent session seen (kept after it ends, for end cards and run summaries). */
  lastSession: Session | null;
}

export const JOINT_WINDOW_S = 10;
export const TEMP_WINDOW_S = 120;

function emptyHist(): JointHistory {
  return { t: [], obs: {}, cmd: {}, clipped: {} };
}

export function initialSnapshot(): StationSnapshot {
  return {
    conn: "connecting",
    status: null,
    joints: null,
    jointHist: emptyHist(),
    telemetry: {},
    tempHist: {},
    limits: {},
    alerts: [],
    calibration: null,
    jobs: {},
    peaks: {},
    alertCount: 0,
    lastSession: null,
  };
}

/** Index of the first sample still inside the window ending at `now`. */
function firstInWindow(ts: readonly number[], now: number, window: number): number {
  let i = 0;
  while (i < ts.length && (ts[i] ?? 0) < now - window) i += 1;
  return i;
}

/** Joint name from a lerobot feature key ("shoulder_pan.pos" → "shoulder_pan"). */
export function jointName(key: string): string {
  return key.endsWith(".pos") ? key.slice(0, -4) : key;
}

export function appendJoints(hist: JointHistory, msg: JointsMsg): JointHistory {
  // A new session restarts `t` at 0: start a fresh window.
  const last = hist.t[hist.t.length - 1];
  const base = last !== undefined && msg.t < last ? emptyHist() : hist;
  const from = firstInWindow(base.t, msg.t, JOINT_WINDOW_S);
  const t = [...base.t.slice(from), msg.t];
  const follower = msg.arms.follower;
  const names = Object.keys(follower).map(jointName);
  const obs: JointHistory["obs"] = {};
  const cmd: JointHistory["cmd"] = {};
  const n = t.length - 1;
  for (const name of names) {
    const prevObs = base.obs[name]?.slice(from) ?? [];
    const prevCmd = base.cmd[name]?.slice(from) ?? [];
    while (prevObs.length < n) prevObs.unshift(null);
    while (prevCmd.length < n) prevCmd.unshift(null);
    obs[name] = [...prevObs, follower[`${name}.pos`] ?? follower[name] ?? null];
    const a = msg.sent ?? msg.action ?? msg.arms.leader;
    cmd[name] = [...prevCmd, a ? (a[`${name}.pos`] ?? a[name] ?? null) : null];
  }
  const clipped: JointHistory["clipped"] = {};
  const t0 = t[0] ?? msg.t;
  for (const [name, ts] of Object.entries(base.clipped)) {
    const keep = ts.filter((x) => x >= t0);
    if (keep.length) clipped[name] = keep;
  }
  for (const c of msg.clipped) {
    const name = jointName(c);
    clipped[name] = [...(clipped[name] ?? []), msg.t];
  }
  return { t, obs, cmd, clipped };
}

function appendTemps(
  hist: StationSnapshot["tempHist"],
  arm: Arm,
  t: number,
  motors: Record<string, MotorSample>,
): StationSnapshot["tempHist"] {
  const armHist = { ...(hist[arm] ?? {}) };
  for (const [motor, s] of Object.entries(motors)) {
    const prev = armHist[motor] ?? { t: [], v: [] };
    const lastT = prev.t[prev.t.length - 1];
    const src = lastT !== undefined && t < lastT ? { t: [], v: [] } : prev;
    const from = firstInWindow(src.t, t, TEMP_WINDOW_S);
    armHist[motor] = { t: [...src.t.slice(from), t], v: [...src.v.slice(from), s.stale ? null : s.temp_c] };
  }
  return { ...hist, [arm]: armHist };
}

/** Drop the message envelope (`type`) from a flat WS message. */
function strip<T extends { type: string }>(msg: T): Omit<T, "type"> {
  return omit(msg, "type");
}

export class StationStore {
  private snap: StationSnapshot = initialSnapshot();
  private listeners = new Set<() => void>();

  getSnapshot = (): StationSnapshot => this.snap;

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  private set(patch: Partial<StationSnapshot>): void {
    this.snap = { ...this.snap, ...patch };
    for (const l of this.listeners) l();
  }

  setConn(conn: ConnState): void {
    if (conn !== this.snap.conn) this.set({ conn });
  }

  setStatus(status: Status): void {
    this.set({ status, lastSession: status.session ?? this.snap.lastSession });
  }

  setJob(job: Job): void {
    this.set({ jobs: { ...this.snap.jobs, [job.id]: job } });
  }

  resetPeaks(): void {
    this.set({ peaks: {}, alertCount: 0 });
  }

  handle(msg: ServerMessage): void {
    switch (msg.type) {
      case "hello":
        this.setStatus(msg.status);
        return;
      case "state":
        this.setStatus(strip(msg));
        return;
      case "joints":
        this.set({ joints: msg, jointHist: appendJoints(this.snap.jointHist, msg) });
        return;
      case "telemetry": {
        const peaks = { ...this.snap.peaks };
        for (const [motor, s] of Object.entries(msg.motors)) {
          const k = `${msg.arm}.${motor}`;
          if (s.temp_c !== null && !s.stale && s.temp_c > (peaks[k] ?? -Infinity)) peaks[k] = s.temp_c;
        }
        this.set({
          telemetry: {
            ...this.snap.telemetry,
            [msg.arm]: { ...this.snap.telemetry[msg.arm], ...msg.motors },
          },
          tempHist: appendTemps(this.snap.tempHist, msg.arm, msg.t, msg.motors),
          limits: { ...this.snap.limits, [msg.arm]: msg.limits },
          peaks,
        });
        return;
      }
      case "alert": {
        const rest = this.snap.alerts.filter((a) => a.id !== msg.id);
        this.set({
          alerts: msg.active ? [...rest, msg] : rest,
          alertCount: this.snap.alertCount + (msg.active ? 1 : 0),
        });
        return;
      }
      case "calibration":
        this.set({ calibration: msg });
        return;
      case "session": {
        const ended = msg.ended === true;
        const session = omit(strip(msg), "ended", "reason", "summary", "loop", "max_temp_c");
        // The final message of a session (`ended: true`) only updates the end card; the `state`
        // message that follows clears `status.session`.
        this.set({
          lastSession: session,
          ...(this.snap.status && !ended ? { status: { ...this.snap.status, session } } : {}),
        });
        return;
      }
      case "job":
        this.setJob(strip(msg));
        return;
      default:
        return;
    }
  }
}
