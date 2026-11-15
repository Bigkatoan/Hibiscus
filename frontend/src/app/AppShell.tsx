import { PxIcon } from "@/hibiscus/PixelAnim";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { useLogout, useMe, useUpdateMe } from "@/api/hooks/auth";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/api/hooks/workspaces";
import { Garden, PixelAnim } from "@/hibiscus/PixelAnim";
import type { AnimName } from "@/hibiscus/sprites.gen";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useWorkspaceEvents } from "@/features/workspace/useWorkspaceEvents";
import { formatRelative } from "@/lib/format";
import { isLanguage, setLanguage, type Language } from "@/lib/i18n";
import { useTheme, type ThemePreference } from "@/lib/theme";
import { cn } from "@/lib/utils";

function WorkspaceSwitcher() {
  const { t } = useTranslation();
  const { slug } = useParams();
  const me = useMe();
  const navigate = useNavigate();
  const memberships = [...(me.data?.memberships ?? [])].sort((a, b) =>
    a.workspace_name.localeCompare(b.workspace_name),
  );
  const current = memberships.find((m) => m.workspace_slug === slug);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          className="min-w-0 max-w-[9rem] justify-between sm:max-w-[14rem]"
          aria-label={t("workspace.switch")}
        >
          <span className="truncate">{current?.workspace_name ?? t("workspace.select")}</span>
          <PxIcon name="chevron_down" className="opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>{t("workspace.switch")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={slug ?? ""}
          onValueChange={(v) => {
            navigate(`/w/${v}/datasets`);
          }}
        >
          {memberships.map((m) => (
            <DropdownMenuRadioItem key={m.workspace_id} value={m.workspace_slug}>
              <span className="truncate">{m.workspace_name}</span>
              <span className="ml-auto text-xs text-muted-foreground">{t(`role.${m.role}`)}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function NotificationsMenu() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { slug } = useParams();
  const q = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const unread = q.data?.pages[0]?.unread_count ?? 0;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={t("notifications.title_count", { count: unread })}
        >
          <PxIcon name="bell" />
          {unread > 0 ? (
            <span className="absolute -right-1 -top-1 min-w-[1.25rem] border-2 border-frame bg-[rgb(215_38_61)] px-0.5 text-center tabular-nums text-sm leading-4 text-white">
              {unread > 99 ? "99+" : unread}
            </span>
          ) : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="flex items-center justify-between px-2 py-1.5">
          <span className="text-sm font-semibold">{t("notifications.title")}</span>
          <Button
            variant="link"
            size="sm"
            className="h-auto p-0"
            disabled={unread === 0}
            onClick={() => markAll.mutate()}
          >
            {t("notifications.mark_all_read")}
          </Button>
        </div>
        <DropdownMenuSeparator />
        {items.length === 0 ? (
          <p className="px-2 py-4 text-center text-sm text-muted-foreground">{t("notifications.empty")}</p>
        ) : null}
        {items.slice(0, 20).map((n) => (
          <DropdownMenuItem
            key={n.id}
            className="flex flex-col items-start gap-0.5"
            onSelect={() => {
              if (!n.read) markRead.mutate(n.id);
              if (n.link?.startsWith("/w/")) navigate(n.link);
              else if (n.link?.startsWith("/") && slug) navigate(`/w/${slug}${n.link}`);
            }}
          >
            <span className={cn("text-sm", !n.read && "font-semibold")}>
              {t(`notifications.kind.${n.kind}`, n.params)}
            </span>
            <span className="text-xs text-muted-foreground">
              {formatRelative(n.created_at, i18n.language)}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function PreferencesMenu() {
  const { t, i18n } = useTranslation();
  const { preference, setPreference } = useTheme();
  const updateMe = useUpdateMe();
  const me = useMe();
  const themeGlyph = preference === "dark" ? "moon" : preference === "light" ? "sun" : "theme_auto";
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={t("prefs.language")}>
            <PxIcon name="language" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuRadioGroup
            value={i18n.language}
            onValueChange={(v) => {
              if (!isLanguage(v)) return;
              setLanguage(v);
              if (me.data) updateMe.mutate({ locale: v satisfies Language });
            }}
          >
            <DropdownMenuRadioItem value="vi" lang="vi">
              Tiếng Việt
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="en" lang="en">
              English
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={t("prefs.theme")}>
            <PxIcon name={themeGlyph} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuRadioGroup
            value={preference}
            onValueChange={(v) => {
              setPreference(v as ThemePreference);
            }}
          >
            <DropdownMenuRadioItem value="light">{t("prefs.theme_light")}</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark">{t("prefs.theme_dark")}</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="system">{t("prefs.theme_system")}</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}

function UserMenu() {
  const { t } = useTranslation();
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const user = me.data?.user;
  if (!user) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("nav.user_menu")}>
          <PxIcon name="user" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="normal-case">
          <span className="block truncate text-sm text-foreground">{user.display_name}</span>
          <span className="block truncate font-normal">{user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/account")}>
          <PxIcon name="gear" />
          {t("nav.account")}
        </DropdownMenuItem>
        {user.is_platform_admin ? (
          <DropdownMenuItem onSelect={() => navigate("/admin")}>
            <PxIcon name="shield" />
            {t("nav.admin")}
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            logout.mutate(undefined, {
              onSettled: () => {
                navigate("/login");
              },
            });
          }}
        >
          <PxIcon name="logout" />
          {t("nav.logout")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Robot-garden metaphor: seed bag = dataset, sprouting pot = run, harvest basket = model. */
const NAV: readonly { to: string; icon: AnimName; label: string }[] = [
  { to: "datasets", icon: "icon_dataset", label: "nav.datasets" },
  { to: "runs", icon: "icon_train", label: "nav.runs" },
  { to: "models", icon: "icon_model", label: "nav.models" },
  { to: "gpus", icon: "icon_gpu", label: "nav.gpus" },
  { to: "settings", icon: "icon_gear", label: "nav.settings" },
];

function SideNav({ slug, onNavigate }: { slug: string; onNavigate?: () => void }) {
  const { t } = useTranslation();
  return (
    <nav aria-label={t("nav.main")} className="flex flex-col gap-2">
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={`/w/${slug}/${item.to}`}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "px-hover flex min-h-11 items-center gap-3 border-2 px-2 py-1 text-base font-extrabold",
              isActive
                ? "border-frame bg-card text-card-foreground shadow"
                : "border-transparent text-sidebar-foreground hover:border-frame hover:bg-card/60",
            )
          }
        >
          <PixelAnim name={item.icon} />
          {t(item.label)}
        </NavLink>
      ))}
    </nav>
  );
}

/** Layout for every authenticated page. */
export function AppShell() {
  const { t } = useTranslation();
  const { slug } = useParams();
  const me = useMe();
  const [mobileOpen, setMobileOpen] = useState(false);
  const wsId = me.data?.memberships.find((m) => m.workspace_slug === slug)?.workspace_id ?? null;
  useWorkspaceEvents(wsId);
  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        {t("nav.skip_to_content")}
      </a>
      <header className="sticky top-0 z-40 border-b-4 border-frame bg-header text-header-foreground shadow-[inset_0_2px_0_0_rgb(255_255_255/0.12)]">
        <div className="flex h-14 items-center gap-1 px-2 sm:gap-2 sm:px-4">
          {slug ? (
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label={mobileOpen ? t("nav.close_menu") : t("nav.open_menu")}
              aria-expanded={mobileOpen}
              aria-controls="mobile-nav"
              onClick={() => {
                setMobileOpen((o) => !o);
              }}
            >
              {mobileOpen ? <PxIcon name="close" /> : <PxIcon name="menu" />}
            </Button>
          ) : null}
          <Link
            to="/"
            aria-label="Hibiscus"
            className="px-hover mr-1 flex shrink-0 items-center gap-2 sm:mr-2"
          >
            <PixelAnim name="hibiscus_sparkle" />
            <span className="hidden font-extrabold text-xl sm:inline" aria-hidden>
              Hibiscus
            </span>
          </Link>
          {me.data?.memberships.length ? <WorkspaceSwitcher /> : null}
          <div className="ml-auto flex shrink-0 items-center">
            <NotificationsMenu />
            <PreferencesMenu />
            <UserMenu />
          </div>
        </div>
      </header>
      <div className="flex">
        {slug ? (
          <aside className="sticky top-[60px] hidden h-[calc(100vh-60px)] w-56 shrink-0 flex-col justify-between border-r-4 border-frame bg-sidebar text-sidebar-foreground md:flex">
            <div className="p-3">
              <SideNav slug={slug} />
            </div>
            <Garden />
          </aside>
        ) : null}
        {slug && mobileOpen ? (
          <div
            id="mobile-nav"
            className="fixed inset-x-0 top-[60px] z-30 border-b-4 border-frame bg-sidebar p-3 text-sidebar-foreground shadow-lg md:hidden"
          >
            <SideNav
              slug={slug}
              onNavigate={() => {
                setMobileOpen(false);
              }}
            />
          </div>
        ) : null}
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
