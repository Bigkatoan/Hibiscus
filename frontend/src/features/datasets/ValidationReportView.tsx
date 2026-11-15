import { PxIcon } from "@/hibiscus/PixelAnim";
import { useTranslation } from "react-i18next";
import type { Schemas } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/misc";
import { cn } from "@/lib/utils";

type Step = Schemas["ValidationStep"];
type Issue = Schemas["ValidationIssue"];

function StepIcon({ status }: { status: Step["status"] }) {
  switch (status) {
    case "passed":
      return <PxIcon name="check" className="text-success" />;
    case "warning":
      return <PxIcon name="warning" className="text-warning" />;
    case "failed":
      return <PxIcon name="close" className="text-destructive" />;
    case "running":
      return <PxIcon name="spinner" className="px-spin text-primary" />;
    case "skipped":
      return <PxIcon name="minus" className="text-muted-foreground" />;
    default:
      return <PxIcon name="pending" className="text-muted-foreground" />;
  }
}

function IssueRow({ issue }: { issue: Issue }) {
  const { t } = useTranslation();
  const params = {
    ...(issue.params ?? {}),
    episode: issue.episode_index,
    path: issue.path,
    feature: issue.feature,
  };
  const glyph = issue.severity === "error" ? "close" : issue.severity === "warning" ? "warning" : "info";
  return (
    <li className="flex gap-2 py-1.5 text-sm">
      <PxIcon
        name={glyph}
        className={cn(
          "mt-0.5 shrink-0",
          issue.severity === "error"
            ? "text-destructive"
            : issue.severity === "warning"
              ? "text-warning"
              : "text-muted-foreground",
        )}
      />
      <div className="min-w-0">
        <p>
          <span className="sr-only">{t(`validation.severity.${issue.severity}`)}: </span>
          {t(`validation.issue.${issue.code}`, params)}
        </p>
        <p className="break-all text-xs text-muted-foreground">
          {issue.episode_index !== null && issue.episode_index !== undefined
            ? `${t("validation.episode", { index: issue.episode_index })} · `
            : ""}
          {issue.feature ? `${issue.feature} · ` : ""}
          {issue.path ?? ""}
        </p>
      </div>
    </li>
  );
}

/** Renders ValidationReport (getValidationReport): 7 steps, issues localised by `code`. */
export function ValidationReportView({ report }: { report: Schemas["ValidationReport"] }) {
  const { t } = useTranslation();
  const { summary } = report;
  const variant =
    summary.result === "passed"
      ? "success"
      : summary.result === "failed"
        ? "destructive"
        : summary.result === "running"
          ? "default"
          : "warning";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Badge variant={variant}>{t(`validation.result.${summary.result}`)}</Badge>
        <span className="text-sm text-muted-foreground">
          {t("validation.counts", { errors: summary.errors, warnings: summary.warnings })}
        </span>
        <span className="text-xs text-muted-foreground">
          LeRobot {report.lerobot_version} · validator {report.validator_version}
        </span>
      </div>
      <ol className="space-y-3">
        {report.steps.map((step) => (
          <li key={step.id} className="rounded-md border p-3">
            <div className="flex items-center gap-3">
              <StepIcon status={step.status} />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{t(`validation.step.${step.id}`)}</p>
                <p className="text-xs text-muted-foreground">{t(`validation.step_status.${step.status}`)}</p>
              </div>
              {step.issues.length > 0 ? (
                <Badge variant="outline">{step.issues.length + (step.issues_truncated ?? 0)}</Badge>
              ) : null}
            </div>
            {step.status === "running" && step.progress !== undefined ? (
              <Progress
                className="mt-2"
                value={step.progress * 100}
                aria-label={t(`validation.step.${step.id}`)}
              />
            ) : null}
            {step.issues.length > 0 ? (
              <ul className="mt-2 divide-y border-t pt-1">
                {step.issues.map((issue, i) => (
                  <IssueRow key={`${issue.code}-${i}`} issue={issue} />
                ))}
              </ul>
            ) : null}
            {step.issues_truncated ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {t("validation.truncated", { count: step.issues_truncated })}
              </p>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
