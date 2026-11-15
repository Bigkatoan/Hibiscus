import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { qk } from "@/api/hooks/keys";
import { ChunkedUploader, type UploaderOptions, type UploadState, type UploadTarget } from "./uploader";

/** React binding for ChunkedUploader; warns before unload while an upload is in flight. */
export function useUploader(options?: UploaderOptions) {
  const qc = useQueryClient();
  const ref = useRef<ChunkedUploader | null>(null);
  const [state, setState] = useState<UploadState | null>(null);
  const optsRef = useRef(options);

  const active = state?.phase === "hashing" || state?.phase === "uploading" || state?.phase === "completing";
  useEffect(() => {
    if (!active) return undefined;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, [active]);

  useEffect(
    () => () => {
      ref.current?.pause();
    },
    [],
  );

  const start = useCallback(
    async (file: File, target: UploadTarget) => {
      ref.current?.pause();
      const up = new ChunkedUploader(file, target, optsRef.current);
      ref.current = up;
      up.subscribe(setState);
      const res = await up.start();
      if (res) {
        await qc.invalidateQueries({ queryKey: qk.datasets(target.workspaceId) });
        await qc.invalidateQueries({ queryKey: qk.datasetVersions(res.dataset.id) });
      }
      return res;
    },
    [qc],
  );

  const resume = useCallback(async () => {
    const up = ref.current;
    if (!up) return null;
    return up.start();
  }, []);

  const pause = useCallback(() => {
    ref.current?.pause();
  }, []);

  const abort = useCallback(async () => {
    await ref.current?.abort();
  }, []);

  const reset = useCallback(() => {
    ref.current?.pause();
    ref.current = null;
    setState(null);
  }, []);

  return { state, start, resume, pause, abort, reset };
}
