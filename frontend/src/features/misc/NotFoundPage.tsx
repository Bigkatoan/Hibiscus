import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Mascot } from "@/components/Mascot";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-12 text-center">
      <Mascot mood="sad" />
      <p className="mt-4 font-extrabold text-2xl text-muted-foreground">404</p>
      <h1 className="mt-2 font-extrabold text-xl">{t("not_found.title")}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("not_found.description")}</p>
      <p className="mt-1 text-sm text-muted-foreground">{t("not_found.hint")}</p>
      <Button asChild className="mt-6">
        <Link to="/">{t("not_found.home")}</Link>
      </Button>
    </div>
  );
}

export function NoWorkspacePage() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-12 text-center">
      <Mascot mood="idle" />
      <h1 className="mt-4 font-extrabold text-xl">{t("workspace.none_title")}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("workspace.none_description")}</p>
    </div>
  );
}
