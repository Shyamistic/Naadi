import { Link } from "react-router";
import { useSettings } from "../../settings/SettingsProvider";
import { useT } from "../../i18n/I18nProvider";
import css from "./pages.module.css";

const feedback = "https://github.com/Shyamistic/Naadi/issues";

export function AboutPage() {
  const { t } = useT();
  return <article className={css.page}><h1>{t("nav.about")}</h1><p>{t("pages.aboutIntro")}</p><h2 id="data">{t("pages.dataPrivacy")}</h2><p>{t("pages.aboutPrivacy")}</p><p>{t("pages.photonPrivacy")}</p><p>{t("pages.credits")}</p><h2 id="accessibility">{t("pages.accessibility")}</h2><p>{t("pages.accessibilityText")}</p><h2 id="terms">{t("pages.terms")}</h2><p>{t("pages.termsText")}</p><p className={css.links}><Link to="/help">{t("pages.helpLink")}</Link> · <a href={feedback} target="_blank" rel="noopener noreferrer">{t("pages.feedback")}</a></p><p className={css.updated}>{t("pages.resultsUpdated")}</p></article>;
}

export function HelpPage() {
  const { t } = useT();
  return <article className={css.page}><h1>{t("nav.help")}</h1><nav aria-label={t("pages.helpContents")} className={css.contents}><a href="#cards">{t("pages.cards")}</a><a href="#dial">{t("pages.dial")}</a><a href="#routes">{t("pages.routesMetro")}</a></nav><section id="cards"><h2>{t("pages.cardsTitle")}</h2><p>{t("pages.cardsText")}</p></section><section id="dial"><h2>{t("pages.dialTitle")}</h2><p>{t("pages.dialText")}</p></section><section id="routes"><h2>{t("pages.routesTitle")}</h2><p>{t("pages.routesText")}</p></section><p className={css.links}><a href={feedback} target="_blank" rel="noopener noreferrer">{t("pages.feedback")}</a></p></article>;
}

export function SettingsPage() {
  const { settings, update, reset } = useSettings();
  const { t } = useT();
  return <article className={css.page}><h1>{t("nav.settings")}</h1><fieldset><legend>{t("pages.language")}</legend><button data-testid="settings-lang-en" aria-pressed={settings.lang === "en"} onClick={() => update({ lang: "en" })}>English</button><button data-testid="settings-lang-hi" aria-pressed={settings.lang === "hi"} onClick={() => update({ lang: "hi" })}>हिन्दी</button></fieldset><fieldset><legend>{t("pages.theme")}</legend><button data-testid="settings-theme-light" aria-pressed={settings.theme === "light"} onClick={() => update({ theme: "light" })}>{t("pages.light")}</button><button data-testid="settings-theme-dark" aria-pressed={settings.theme === "dark"} onClick={() => update({ theme: "dark" })}>{t("pages.dark")}</button></fieldset><fieldset><legend>{t("pages.textSize")}</legend>{([100,112,125] as const).map(size => <button key={size} data-testid={`settings-text-${size}`} aria-pressed={settings.textSize === size} onClick={() => update({ textSize: size })}>{size}%</button>)}</fieldset><label className={css.check}><input data-testid="settings-reduced-motion" type="checkbox" checked={settings.reduceMotion} onChange={event => update({ reduceMotion: event.target.checked })} /> {t("pages.reduceMotion")}</label><button className={css.reset} data-testid="settings-reset" onClick={reset}>{t("pages.reset")}</button></article>;
}

export function ErrorPage() { const { t } = useT(); return <article className={css.page}><h1>{t("pages.error")}</h1><p>{t("pages.errorText")}</p><button data-testid="error-reload" onClick={() => location.reload()}>{t("pages.reload")}</button></article>; }
export function NotFound() { const { t } = useT(); return <article className={css.page}><h1>{t("pages.notFound")}</h1><p>{t("pages.notFoundText")}</p><Link to="/" data-testid="notfound-plan">{t("pages.planJourney")}</Link></article>; }
