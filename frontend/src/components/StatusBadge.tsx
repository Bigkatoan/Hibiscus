import { useTranslation } from "react-i18next";
import type { Schemas } from "@/api/client";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { Badge, type BadgeProps } from "@/components/ui/badge";

type Variant = NonNullable<BadgeProps["variant"]>;

const RUN_VARIANT: Record<Schemas["RunStatus"], Variant> = {
  queued: "secondary",
  preparing: "secondary",
  running: "default",
  pausing: "warning",
  paused: "warning",
  exporting: "default",
  succeeded: "success",
  failed: "destructive",
  cancelling: "warning",
  cancelled: "outline",
};

const ACTIVE = new Set([
  "preparing",
  "running",
  "exporting",
  "pausing",
  "cancelling",
  "unpacking",
  "validating",
  "building",
]);

/** 8×8 status glyphs inside the chip: dashed ring = waiting, warning = failed, check = done; stepped spinner = busy. */
function Icon({ status }: { status: string }) {
  if (ACTIVE.has(status)) return <PxIcon name="spinner" className="px-spin" />;
  if (status === "failed" || status === "invalid") return <PxIcon name="warning" />;
  if (status === "paused") return <PxIcon name="pause" />;
  if (status === "queued" || status === "pending") return <PxIcon name="pending" />;
  if (status === "succeeded" || status === "ready") return <PxIcon name="check" />;
  return null;
}

export function RunStatusBadge({ status }: { status: Schemas["RunStatus"] }) {
  const { t } = useTranslation();
  return (
    <Badge variant={RUN_VARIANT[status]}>
      <Icon status={status} />
      {t(`run.status.${status}`)}
    </Badge>
  );
}

const VERSION_VARIANT: Record<Schemas["DatasetVersionStatus"], Variant> = {
  pending: "secondary",
  unpacking: "secondary",
  validating: "default",
  ready: "success",
  invalid: "destructive",
  failed: "destructive",
};

export function VersionStatusBadge({ status }: { status: Schemas["DatasetVersionStatus"] }) {
  const { t } = useTranslation();
  return (
    <Badge variant={VERSION_VARIANT[status]}>
      <Icon status={status} />
      {t(`dataset.status.${status}`)}
    </Badge>
  );
}

const MODEL_VARIANT: Record<Schemas["ModelStatus"], Variant> = {
  pending: "secondary",
  building: "default",
  ready: "success",
  failed: "destructive",
};

export function ModelStatusBadge({ status }: { status: Schemas["ModelStatus"] }) {
  const { t } = useTranslation();
  return (
    <Badge variant={MODEL_VARIANT[status]}>
      <Icon status={status} />
      {t(`model.status.${status}`)}
    </Badge>
  );
}

export function VerifiedBadge({ verified }: { verified: boolean }) {
  const { t } = useTranslation();
  return verified ? (
    <Badge variant="success">
      <PxIcon name="check" />
      {t("model.verified")}
    </Badge>
  ) : (
    <Badge variant="outline">
      <PxIcon name="warning" />
      {t("model.not_verified")}
    </Badge>
  );
}

const JOB_VARIANT: Record<Schemas["JobStatus"], Variant> = {
  queued: "secondary",
  running: "default",
  succeeded: "success",
  failed: "destructive",
  cancelled: "outline",
};

export function JobStatusBadge({ status }: { status: Schemas["JobStatus"] }) {
  const { t } = useTranslation();
  return (
    <Badge variant={JOB_VARIANT[status]}>
      <Icon status={status === "running" ? "running" : status} />
      {t(`job.status.${status}`)}
    </Badge>
  );
}
