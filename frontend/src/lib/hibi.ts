import type { Schemas } from "@/api/client";
import type { HibiMood } from "@/hibiscus/PixelAnim";

export type { HibiMood };

/** Every mood the synced Hibi (robot arm holding a hibiscus) is drawn in. */
export const HIBI_MOODS: readonly HibiMood[] = ["idle", "wave", "happy", "working", "sleep", "sad"];

/**
 * Run status → Hibi mood (hibiscus-assets style guide): queued/paused sleep, running works,
 * succeeded is happy, failed is sad; cancelled/cancelling go back to idle.
 */
export const RUN_HIBI: Record<Schemas["RunStatus"], HibiMood> = {
  queued: "sleep",
  preparing: "working",
  running: "working",
  exporting: "working",
  pausing: "sleep",
  paused: "sleep",
  succeeded: "happy",
  failed: "sad",
  cancelling: "idle",
  cancelled: "idle",
};

export function hibiForRunStatus(status: Schemas["RunStatus"]): HibiMood {
  return RUN_HIBI[status];
}
