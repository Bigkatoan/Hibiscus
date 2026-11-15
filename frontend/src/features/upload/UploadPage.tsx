import { PxIcon } from "@/hibiscus/PixelAnim";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useActiveUploads, useDatasets } from "@/api/hooks/datasets";
import { ErrorAlert, PageHeader } from "@/components/common";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Alert, Progress } from "@/components/ui/misc";
import { useWorkspace, useWsPath } from "@/features/workspace/context";
import { formatBytes, formatDateTime, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { inferArchiveFormat, type UploaderOptions } from "./uploader";
import { useUploader } from "./useUploader";

const ACCEPT = ".zip,.tar,.tar.gz,.tgz,.tar.zst,.tzst,.rar";

export function datasetNameFromFile(filename: string): string {
  const base = filename.replace(/\.(tar\.gz|tar\.zst|tgz|tzst|zip|tar|rar)$/i, "");
  return base.replace(/\p{Cc}/gu, "").slice(0, 100) || "dataset";
}

/** Dataset upload (ADR-0010): hash in a Web Worker, chunked resumable upload, then validation. */
export function UploadPage({ uploaderOptions }: { uploaderOptions?: UploaderOptions }) {
  const { t, i18n } = useTranslation();
  const ws = useWorkspace();
  const path = useWsPath();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const datasets = useDatasets(ws.workspace_id, "");
  const activeUploads = useActiveUploads(ws.workspace_id);
  const { state, start, resume, pause, abort, reset } = useUploader(uploaderOptions);
  const [file, setFile] = useState<File | null>(null);
  const [target, setTarget] = useState<string>(params.get("dataset") ?? "new");
  const [name, setName] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setName(datasetNameFromFile(f.name));
  };

  const existing = datasets.data?.pages.flatMap((p) => p.items) ?? [];
  const busy = state && ["hashing", "initializing", "uploading", "completing"].includes(state.phase);
  const formatOk = file ? inferArchiveFormat(file.name) !== null : true;

  const begin = () => {
    if (!file) return;
    void start(file, {
      workspaceId: ws.workspace_id,
      ...(target === "new"
        ? { newDatasetName: name.trim() || datasetNameFromFile(file.name) }
        : { datasetId: target }),
    });
  };

  const result = state?.result;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t("upload.title")} description={t("upload.description")} />
      {!state ? (
        <Card>
          <CardContent className="space-y-5 pt-6">
            <div
              className={cn(
                "flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors",
                dragOver ? "border-primary bg-primary/5" : "border-input",
              )}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => {
                setDragOver(false);
              }}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                pick(e.dataTransfer.files[0]);
              }}
            >
              <PxIcon name="upload" className="mb-2 text-muted-foreground" />
              <p className="text-sm">{t("upload.drop_here")}</p>
              <label htmlFor={inputId} className="mt-3">
                <span className="sr-only">{t("upload.choose_file")}</span>
                <input
                  ref={inputRef}
                  id={inputId}
                  type="file"
                  accept={ACCEPT}
                  className="block text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-primary-foreground"
                  onChange={(e) => {
                    pick(e.target.files?.[0]);
                  }}
                />
              </label>
              <p className="mt-2 text-xs text-muted-foreground">{t("upload.formats")}</p>
            </div>
            {file ? (
              <div className="flex items-center gap-3 rounded-md border p-3 text-sm">
                <PxIcon name="box" className="shrink-0" />
                <span className="min-w-0 flex-1 truncate font-medium">{file.name}</span>
                <span className="text-muted-foreground">{formatBytes(file.size, i18n.language)}</span>
              </div>
            ) : null}
            {!formatOk ? <Alert variant="destructive">{t("errors.archive_format_unsupported")}</Alert> : null}
            <Field label={t("upload.target")}>
              <NativeSelect
                value={target}
                onChange={(e) => {
                  setTarget(e.target.value);
                }}
              >
                <option value="new">{t("upload.new_dataset")}</option>
                {existing.map((d) => (
                  <option key={d.id} value={d.id}>
                    {t("upload.new_version_of", { name: d.name })}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {target === "new" ? (
              <Field label={t("datasets.name")} required>
                <Input
                  value={name}
                  maxLength={100}
                  onChange={(e) => {
                    setName(e.target.value);
                  }}
                />
              </Field>
            ) : null}
            <Button
              size="lg"
              className="w-full"
              disabled={!file || !formatOk || (target === "new" && !name.trim())}
              onClick={begin}
            >
              <PxIcon name="upload" />
              {t("upload.start")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="truncate">{file?.name}</CardTitle>
            <CardDescription>
              {state.resumed ? t("upload.resumed") : null} {t(`upload.phase.${state.phase}`)}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div aria-live="polite" className="space-y-3">
              <div>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{t("upload.hashing")}</span>
                  <span>
                    {formatPercent(
                      state.totalBytes ? state.hashedBytes / state.totalBytes : 1,
                      i18n.language,
                    )}
                  </span>
                </div>
                <Progress
                  value={state.totalBytes ? (state.hashedBytes / state.totalBytes) * 100 : 100}
                  aria-label={t("upload.hashing")}
                />
              </div>
              <div>
                <div className="mb-1 flex justify-between text-sm">
                  <span>
                    {t("upload.uploading")}{" "}
                    {state.partCount
                      ? t("upload.parts", { done: state.partsDone, total: state.partCount })
                      : null}
                  </span>
                  <span>
                    {formatBytes(state.uploadedBytes, i18n.language)} /{" "}
                    {formatBytes(state.totalBytes, i18n.language)}
                  </span>
                </div>
                <Progress
                  value={state.totalBytes ? (state.uploadedBytes / state.totalBytes) * 100 : 0}
                  aria-label={t("upload.uploading")}
                />
              </div>
            </div>
            <ErrorAlert error={state.error} />
            {state.phase === "done" && result ? (
              <Alert variant="success">
                <p className="mb-3">
                  {t("upload.done", { name: result.dataset.name, version: result.version.version })}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button asChild>
                    <Link to={path(`runs/new?version=${result.version.id}`)}>
                      <PxIcon name="sprout" />
                      {t("upload.train_now")}
                    </Link>
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => navigate(path(`datasets/${result.dataset.id}?v=${result.version.id}`))}
                  >
                    {t("upload.view_validation")}
                  </Button>
                </div>
              </Alert>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {busy ? (
                <Button variant="outline" onClick={pause}>
                  <PxIcon name="pause" />
                  {t("upload.pause")}
                </Button>
              ) : null}
              {state.phase === "paused" || state.phase === "error" ? (
                <Button onClick={() => void resume()}>
                  <PxIcon name="play" />
                  {t("upload.resume")}
                </Button>
              ) : null}
              {state.phase !== "done" && state.phase !== "aborted" ? (
                <Button variant="ghost" onClick={() => void abort()}>
                  <PxIcon name="close" />
                  {t("upload.cancel")}
                </Button>
              ) : null}
              {state.phase === "aborted" || state.phase === "done" ? (
                <Button
                  variant="outline"
                  onClick={() => {
                    reset();
                    setFile(null);
                  }}
                >
                  {t("upload.another")}
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>
      )}
      {!state && (activeUploads.data?.items.length ?? 0) > 0 ? (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>{t("upload.unfinished")}</CardTitle>
            <CardDescription>{t("upload.unfinished_help")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {activeUploads.data?.items.map((u) => (
                <li
                  key={u.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded border p-2"
                >
                  <span className="truncate font-medium">{u.filename}</span>
                  <span className="text-muted-foreground">
                    {formatBytes(u.bytes_received ?? 0, i18n.language)} / {formatBytes(u.size, i18n.language)}{" "}
                    · {t("upload.expires", { date: formatDateTime(u.expires_at, i18n.language) })}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
