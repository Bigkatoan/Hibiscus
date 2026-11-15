import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Mascot } from "@/components/Mascot";
import { Petals, Sprite } from "@/hibiscus/PixelAnim";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";

/** Guest pages (login, reset, invite): Hibi waves above the panel, petals drift down, grass along the bottom. */
export function AuthLayout({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <main id="main" className="relative flex min-h-screen flex-col">
      <Petals count={10} />
      <div className="relative flex flex-1 items-center justify-center px-4 py-8">
        <div className="w-full max-w-md">
          <div className="mb-4 flex items-end justify-center gap-4">
            <Mascot mood="wave" />
            <div className="pb-2">
              <p className="flex items-center gap-2">
                <Sprite name="hibiscus" />
                <span className="font-extrabold text-2xl">Hibiscus</span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{t("brand.tagline")}</p>
            </div>
          </div>
          <Card>
            <CardHeader>
              <h1 className="font-extrabold text-xl">{title}</h1>
              {description ? <CardDescription>{description}</CardDescription> : null}
            </CardHeader>
            <CardContent>{children}</CardContent>
          </Card>
        </div>
      </div>
      <div className="px-grass h-8 shrink-0 border-t-2 border-frame" aria-hidden />
    </main>
  );
}

/** Tokens in emailed links may arrive as `?token=`, `#token=` or a path segment. */
export function readLinkToken(search: string, hash: string, pathToken?: string): string | null {
  if (pathToken) return pathToken;
  const q = new URLSearchParams(search).get("token");
  if (q) return q;
  const h = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return h ?? null;
}
