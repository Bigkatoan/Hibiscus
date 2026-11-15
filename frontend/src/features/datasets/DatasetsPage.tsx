import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { useDatasets, useImportHf } from "@/api/hooks/datasets";
import { EmptyState, ErrorAlert, LoadMore, PageHeader, PageLoader } from "@/components/common";
import { Field } from "@/components/Field";
import { VersionStatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { useCan, useWorkspace, useWsPath } from "@/features/workspace/context";
import { formatBytes, formatInt, formatRelative } from "@/lib/format";

export const HF_URI_RE = /^hf:\/\/[A-Za-z0-9][\w.-]*\/[\w.-]+(@[\w./-]+)?$/;

function ImportHfDialog() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const path = useWsPath();
  const navigate = useNavigate();
  const importHf = useImportHf();
  const [open, setOpen] = useState(false);
  const form = useForm<{ hf_uri: string; name: string }>({ defaultValues: { hf_uri: "", name: "" } });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <PxIcon name="download" />
          {t("datasets.import_hf")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("datasets.import_hf")}</DialogTitle>
          <DialogDescription>{t("datasets.import_hf_help")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          noValidate
          onSubmit={(e) =>
            void form
              .handleSubmit(async (v) => {
                const res = await importHf.mutateAsync({
                  workspace_id: ws.workspace_id,
                  hf_uri: v.hf_uri.trim(),
                  new_dataset_name: v.name.trim() || (v.hf_uri.split("/").pop()?.split("@")[0] ?? "dataset"),
                });
                setOpen(false);
                navigate(path(`datasets/${res.dataset.id}?v=${res.version.id}`));
              })(e)
              .catch(() => undefined)
          }
        >
          <Field
            label={t("datasets.hf_uri")}
            required
            description="hf://lerobot/svla_so101_pickplace@main"
            error={form.formState.errors.hf_uri ? t("errors.hf_uri_invalid") : undefined}
          >
            <Input
              autoComplete="off"
              spellCheck={false}
              {...form.register("hf_uri", { required: true, pattern: HF_URI_RE })}
            />
          </Field>
          <Field label={t("datasets.name")}>
            <Input autoComplete="off" {...form.register("name", { maxLength: 100 })} />
          </Field>
          <ErrorAlert error={importHf.error} />
          <Button type="submit" disabled={importHf.isPending}>
            {t("datasets.import_start")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** listDatasets with search + cursor pagination. */
export function DatasetsPage() {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const path = useWsPath();
  const canWrite = useCan("member");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const list = useDatasets(ws.workspace_id, search);
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title={t("datasets.title")}
        description={t("datasets.description")}
        actions={
          canWrite ? (
            <>
              <ImportHfDialog />
              <Button asChild>
                <Link to={path("datasets/upload")}>
                  <PxIcon name="upload" />
                  {t("datasets.upload")}
                </Link>
              </Button>
            </>
          ) : null
        }
      />
      <form
        role="search"
        className="mb-4 flex max-w-md gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(q.trim());
        }}
      >
        <label htmlFor="dataset-search" className="sr-only">
          {t("common.search")}
        </label>
        <Input
          id="dataset-search"
          type="search"
          placeholder={t("datasets.search_placeholder")}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
          }}
        />
        <Button type="submit" variant="outline" size="icon" aria-label={t("common.search")}>
          <PxIcon name="search" />
        </Button>
      </form>
      {list.isPending ? <PageLoader /> : null}
      <ErrorAlert error={list.error} />
      {list.isSuccess && items.length === 0 ? (
        <EmptyState
          title={t("datasets.empty")}
          description={t("datasets.empty_help")}
          action={
            canWrite ? (
              <Button asChild>
                <Link to={path("datasets/upload")}>{t("datasets.upload")}</Link>
              </Button>
            ) : undefined
          }
        />
      ) : null}
      {items.length > 0 ? (
        <Table>
          <THead>
            <TR>
              <TH>{t("datasets.name")}</TH>
              <TH>{t("datasets.latest_version")}</TH>
              <TH>{t("datasets.episodes")}</TH>
              <TH>{t("datasets.frames")}</TH>
              <TH>{t("datasets.size")}</TH>
              <TH>{t("common.updated")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((d) => (
              <TR key={d.id}>
                <TD>
                  <Link to={path(`datasets/${d.id}`)} className="font-medium text-primary hover:underline">
                    {d.name}
                  </Link>
                  {d.description ? (
                    <p className="max-w-md truncate text-xs text-muted-foreground">{d.description}</p>
                  ) : null}
                </TD>
                <TD>
                  {d.latest_version ? (
                    <span className="flex items-center gap-2">
                      v{d.latest_version.version} <VersionStatusBadge status={d.latest_version.status} />
                    </span>
                  ) : (
                    "—"
                  )}
                </TD>
                <TD>{formatInt(d.latest_version?.total_episodes, i18n.language)}</TD>
                <TD>{formatInt(d.latest_version?.total_frames, i18n.language)}</TD>
                <TD>{formatBytes(d.latest_version?.size_bytes, i18n.language)}</TD>
                <TD>{formatRelative(d.updated_at, i18n.language)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}
      <LoadMore
        hasNextPage={list.hasNextPage}
        isFetchingNextPage={list.isFetchingNextPage}
        fetchNextPage={list.fetchNextPage}
      />
    </div>
  );
}
