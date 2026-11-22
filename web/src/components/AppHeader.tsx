import { useState } from "react";
import { Link, NavLink } from "react-router";
import { Menu, Moon, Settings, Sun, CircleHelp } from "../ui/icons";
import { IconButton } from "../ui/primitives";
import { Logo } from "./Logo";
import { useSettings } from "../settings/SettingsProvider";
import { useT } from "../i18n/I18nProvider";
import { useHealth } from "../api/queries";
import { fmtCount } from "../i18n/format";
import type { TranslationKey } from "../i18n/index";

// In-app links (NavLink/Link) switch pages without reloading the app, so the map and data stay loaded.
const NAV: readonly (readonly [string, string, TranslationKey])[] = [["/", "nav-plan", "nav.plan"], ["/live", "nav-live", "nav.live"], ["/speeds", "nav-speeds", "nav.speeds"], ["/accuracy", "nav-accuracy", "nav.accuracy"], ["/about", "nav-about", "nav.about"]];

export function AppHeader() {
  const { settings, update } = useSettings();
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const health = useHealth();
  const buses = health.data?.live?.buses;
  const close = () => setOpen(false);
  return <>
    <header className="header">
      <Logo />
      <nav className="nav" aria-label="Primary">{NAV.map(([href, id, key]) => <NavLink key={href} to={href} end={href === "/"} data-testid={id}>{t(key)}</NavLink>)}</nav>
      <Link className="live-chip" to="/live" data-testid="header-live-chip"><i aria-hidden="true" />{buses ? t("shell.liveCount", { count: fmtCount(buses) }) : t("shell.liveBuses")}</Link>
      <div className="header-actions">
        <button className="lang-toggle" data-testid="header-lang" onClick={() => update({ lang: settings.lang === "en" ? "hi" : "en" })}>{settings.lang === "en" ? "हिन्दी" : "English"}</button>
        <IconButton testId="header-theme" label={t("shell.toggleTheme")} icon={settings.theme === "light" ? <Moon size={20} /> : <Sun size={20} />} onClick={() => update({ theme: settings.theme === "light" ? "dark" : "light" })} />
        <Link to="/help" data-testid="header-help" aria-label={t("shell.help")}><CircleHelp size={20} /></Link>
        <Link to="/settings" data-testid="header-settings" aria-label={t("shell.settings")}><Settings size={20} /></Link>
        <IconButton testId="header-menu" label={t("shell.menu")} icon={<Menu size={20} />} onClick={() => setOpen(true)} />
      </div>
    </header>
    {open && <div className="drawer-backdrop" onClick={close}><aside className="drawer" role="dialog" aria-label={t("shell.menu")} onClick={(event) => event.stopPropagation()}>
      <button data-testid="drawer-close" aria-label={t("shell.close")} onClick={close}>{t("shell.close")}</button>
      {NAV.map(([href, id, key]) => <NavLink key={href} to={href} end={href === "/"} data-testid={`drawer-${id.slice(4)}`} onClick={close}>{t(key)}</NavLink>)}
      <NavLink to="/help" data-testid="drawer-help" onClick={close}>{t("nav.help")}</NavLink>
      <NavLink to="/settings" data-testid="drawer-settings" onClick={close}>{t("nav.settings")}</NavLink>
      <button data-testid="drawer-theme-light" onClick={() => update({ theme: "light" })}>{t("shell.light")}</button>
      <button data-testid="drawer-theme-dark" onClick={() => update({ theme: "dark" })}>{t("shell.dark")}</button>
      <button data-testid="drawer-lang-en" onClick={() => update({ lang: "en" })}>English</button>
      <button data-testid="drawer-lang-hi" onClick={() => update({ lang: "hi" })}>हिन्दी</button>
    </aside></div>}
  </>;
}
