import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { HibiMood } from "@/lib/hibi";
import { Mascot } from "@/components/Mascot";
import { Button, type ButtonProps } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Alert, AlertTitle } from "@/components/ui/misc";
import { errorKey } from "@/lib/errors";
import { cn } from "@/lib/utils";

export function Spinner({ className, label }: { className?: string; label?: string }) {
  const { t } = useTranslation();
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-muted-foreground", className)}>
      <PxIcon name="spinner" className="px-spin" />
      <span className="sr-only">{label ?? t("common.loading")}</span>
    </span>
  );
}

export function PageLoader() {
  return (
    <div className="flex min-h-[30vh] items-center justify-center">
      <Spinner />
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 max-w-full">
        <h1 className="min-w-0 font-extrabold text-2xl [overflow-wrap:anywhere]">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

/** Empty list: Hibi waits in the garden (idle, blinking) with a short hint and an action. */
export function EmptyState({
  title,
  description,
  action,
  mood = "idle",
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  mood?: HibiMood;
}) {
  return (
    <div className="flex flex-col items-center justify-center border-2 border-dashed border-frame/40 px-4 py-8 text-center">
      <Mascot mood={mood} className="mb-3" />
      <p className="font-extrabold text-base">{title}</p>
      {description ? <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/** Localised error from an ApiError `code` (never the server `detail`). */
export function ErrorAlert({ error, className }: { error: unknown; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  const { key, params } = errorKey(error);
  const requestId =
    typeof error === "object" && "requestId" in error
      ? (error as { requestId?: string }).requestId
      : undefined;
  return (
    <Alert variant="destructive" className={className}>
      <div className="flex gap-2">
        <PxIcon name="warning" className="mt-0.5 shrink-0" />
        <div>
          <AlertTitle>{t(key, { ...params, defaultValue: t("errors.unknown_error") })}</AlertTitle>
          {requestId ? (
            <p className="text-xs text-muted-foreground">{t("errors.request_id", { id: requestId })}</p>
          ) : null}
        </div>
      </div>
    </Alert>
  );
}

export function CopyButton({ value, label }: { value: string; label?: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => {
            setCopied(false);
          }, 1500);
        });
      }}
    >
      {copied ? <PxIcon name="check" /> : <PxIcon name="copy" />}
      {copied ? t("common.copied") : (label ?? t("common.copy"))}
    </Button>
  );
}

export interface ConfirmButtonProps extends Omit<ButtonProps, "onClick"> {
  title: string;
  description?: string;
  confirmLabel: string;
  onConfirm: () => unknown;
  destructive?: boolean;
}

/** Button that asks for confirmation in an accessible dialog before running `onConfirm`. */
export function ConfirmButton({
  title,
  description,
  confirmLabel,
  onConfirm,
  destructive = false,
  children,
  ...buttonProps
}: ConfirmButtonProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        setError(null);
      }}
    >
      <DialogTrigger asChild>
        <Button {...buttonProps}>{children}</Button>
      </DialogTrigger>
      <DialogContent {...(description ? {} : { "aria-describedby": undefined })}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <ErrorAlert error={error} />
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              setOpen(false);
            }}
          >
            {t("common.cancel")}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await onConfirm();
                setOpen(false);
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? <PxIcon name="spinner" className="px-spin" /> : null}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function LoadMore({
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
}: {
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => unknown;
}) {
  const { t } = useTranslation();
  if (!hasNextPage) return null;
  return (
    <div className="mt-4 flex justify-center">
      <Button variant="outline" onClick={() => void fetchNextPage()} disabled={isFetchingNextPage}>
        {isFetchingNextPage ? <PxIcon name="spinner" className="px-spin" /> : null}
        {t("common.load_more")}
      </Button>
    </div>
  );
}

export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-4 text-sm sm:gap-x-6 lg:grid-cols-3">
      {items.map(([k, v], i) => (
        <div key={i} className="min-w-0">
          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{k}</dt>
          <dd className="mt-0.5 break-words font-medium">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
