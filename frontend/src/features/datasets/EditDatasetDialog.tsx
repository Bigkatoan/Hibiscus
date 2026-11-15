import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import type { Schemas } from "@/api/client";
import { useUpdateDataset } from "@/api/hooks/datasets";
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
import { Input, Textarea } from "@/components/ui/input";

/** updateDataset: rename / edit description (dataset_name_taken is mapped to the name field). */
export function EditDatasetDialog({ dataset }: { dataset: Schemas["Dataset"] }) {
  const { t } = useTranslation();
  const update = useUpdateDataset(dataset.id);
  const [open, setOpen] = useState(false);
  const form = useForm<{ name: string; description: string }>({
    values: { name: dataset.name, description: dataset.description },
  });
  const nameTaken = update.error && "code" in update.error && update.error.code === "dataset_name_taken";
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        update.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <PxIcon name="edit" />
          {t("datasets.edit")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("datasets.edit")}</DialogTitle>
          <DialogDescription>{t("datasets.edit_help")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) =>
            void form
              .handleSubmit(async (v) => {
                await update.mutateAsync({ name: v.name.trim(), description: v.description });
                setOpen(false);
              })(e)
              .catch(() => undefined)
          }
        >
          <Field
            label={t("datasets.name")}
            required
            error={nameTaken ? t("errors.dataset_name_taken") : undefined}
          >
            <Input maxLength={100} {...form.register("name", { required: true })} />
          </Field>
          <Field label={t("datasets.description_label")}>
            <Textarea rows={3} {...form.register("description")} />
          </Field>
          {!nameTaken ? <ErrorAlert error={update.error} /> : null}
          <Button type="submit" disabled={update.isPending}>
            {t("common.save")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
