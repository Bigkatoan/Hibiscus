import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useCreateWorkspace } from "@/api/hooks/workspaces";
import { ErrorAlert } from "@/components/common";
import { Field } from "@/components/Field";
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

/** Contract `Slug`: ^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$ */
export const SLUG_RE = /^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$/;

export function slugify(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/gi, "d")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/g, "");
}

/** createWorkspace (platform admins only in v1); the creator becomes owner. */
export function CreateWorkspaceDialog() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useCreateWorkspace();
  const [open, setOpen] = useState(false);
  const form = useForm<{ name: string; slug: string }>({ defaultValues: { name: "", slug: "" } });
  const slugTaken = create.error instanceof ApiError && create.error.code === "workspace_slug_taken";
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <PxIcon name="plus" />
          {t("admin.create_workspace")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("admin.create_workspace")}</DialogTitle>
          <DialogDescription>{t("admin.create_workspace_help")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          noValidate
          onSubmit={(e) =>
            void form
              .handleSubmit(async (v) => {
                const ws = await create.mutateAsync({ name: v.name.trim(), slug: v.slug });
                setOpen(false);
                navigate(`/w/${ws.slug}/settings`);
              })(e)
              .catch(() => undefined)
          }
        >
          <Field label={t("workspace.name")} required>
            <Input
              maxLength={100}
              {...form.register("name", {
                required: true,
                onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
                  if (!form.formState.dirtyFields.slug) form.setValue("slug", slugify(e.target.value));
                },
              })}
            />
          </Field>
          <Field
            label={t("admin.workspace_slug")}
            required
            description={t("admin.workspace_slug_help")}
            error={
              form.formState.errors.slug
                ? t("admin.workspace_slug_invalid")
                : slugTaken
                  ? t("errors.workspace_slug_taken")
                  : undefined
            }
          >
            <Input spellCheck={false} {...form.register("slug", { required: true, pattern: SLUG_RE })} />
          </Field>
          {!slugTaken ? <ErrorAlert error={create.error} /> : null}
          <Button type="submit" disabled={create.isPending}>
            {t("admin.create_workspace")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
