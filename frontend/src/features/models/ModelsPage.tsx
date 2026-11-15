import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { apiUrl, type Schemas } from "@/api/client";
import { useModels } from "@/api/hooks/models";
import { EmptyState, ErrorAlert, LoadMore, PageHeader, PageLoader } from "@/components/common";
import { ModelStatusBadge, VerifiedBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox, Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { useWorkspace, useWsPath } from "@/features/workspace/context";
import { formatBytes, formatInt, formatNumber, formatRelative } from "@/lib/format";

export function OnnxBadge({ status }: { status: Schemas["OnnxStatus"] }) {
  const { t } = useTranslation();
  const variant =
    status === "passed"
      ? "success"
      : status === "failed"
        ? "destructive"
        : status === "not_supported"
          ? "outline"
          : "secondary";
  return <Badge variant={variant}>ONNX: {t(`model.onnx.${status}`)}</Badge>;
}

export function modelDownloadUrl(id: string): string {
  return apiUrl(`/models/${id}/download`);
}

/** listModels with verified filter + direct bundle download. */
export function ModelsPage() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const path = useWsPath();
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [q, setQ] = useState("");
  const models = useModels(ws.workspace_id, {
    ...(verifiedOnly ? { verified: true } : {}),
    ...(q.trim() ? { q: q.trim() } : {}),
  });
  const items = models.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title={t("models.title")} description={t("models.description")} />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-sm">
          <span className="block font-medium">{t("common.search")}</span>
          <Input
            type="search"
            className="w-56"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
            }}
          />
        </label>
        <label className="flex items-center gap-2 pb-2 text-sm">
          <Checkbox
            checked={verifiedOnly}
            onChange={(e) => {
              setVerifiedOnly(e.target.checked);
            }}
          />
          {t("models.verified_only")}
        </label>
      </div>
      {models.isPending ? <PageLoader /> : null}
      <ErrorAlert error={models.error} />
      {models.isSuccess && items.length === 0 ? (
        <EmptyState title={t("models.empty")} description={t("models.empty_help")} />
      ) : null}
      {items.length > 0 ? (
        <Table>
          <THead>
            <TR>
              <TH>{t("models.name")}</TH>
              <TH>{t("common.status")}</TH>
              <TH>{t("runs.policy")}</TH>
              <TH>{t("models.run")}</TH>
              <TH>{t("models.mae")}</TH>
              <TH>{t("datasets.size")}</TH>
              <TH>{t("common.created")}</TH>
              <TH>
                <span className="sr-only">{t("common.actions")}</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {items.map((m) => (
              <TR key={m.id}>
                <TD>
                  <Link to={path(`models/${m.id}`)} className="font-medium text-primary hover:underline">
                    {m.name}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {t("models.step", { step: formatInt(m.step, i18n.language) })}
                  </p>
                </TD>
                <TD>
                  <div className="flex flex-wrap gap-1">
                    <ModelStatusBadge status={m.status} />
                    {m.status === "ready" ? <VerifiedBadge verified={m.verified} /> : null}
                    <OnnxBadge status={m.onnx_status} />
                  </div>
                </TD>
                <TD className="uppercase">{m.policy_type}</TD>
                <TD>
                  <Link className="hover:underline" to={path(`runs/${m.run_id}`)}>
                    #{m.run_number}
                  </Link>
                </TD>
                <TD>{formatNumber(m.eval_summary?.action_mae ?? null, i18n.language)}</TD>
                <TD>{formatBytes(m.bundle_size_bytes, i18n.language)}</TD>
                <TD>{formatRelative(m.created_at, i18n.language)}</TD>
                <TD className="text-right">
                  {m.status === "ready" ? (
                    <Button variant="ghost" size="sm" asChild>
                      <a
                        href={modelDownloadUrl(m.id)}
                        aria-label={t("models.download_name", { name: m.name })}
                      >
                        <PxIcon name="download" />
                      </a>
                    </Button>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}
      {items.some((m) => m.eval_summary) ? (
        <p className="text-xs text-muted-foreground" data-testid="mae-disclaimer">
          {t("models.mae")}: {t("eval.offline_not_success_rate")}
        </p>
      ) : null}
      <LoadMore
        hasNextPage={models.hasNextPage}
        isFetchingNextPage={models.isFetchingNextPage}
        fetchNextPage={models.fetchNextPage}
      />
    </div>
  );
}
