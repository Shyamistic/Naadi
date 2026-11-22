import { Link } from "react-router";
import { useT } from "../i18n/I18nProvider";

export function Footer() {
  const { t } = useT();
  return <footer><div>Data: Delhi Transport Stack · Delhi Open Transit Data · Map © OpenStreetMap contributors</div><div><Link to="/about" data-testid="footer-about">{t("nav.about")}</Link> · <Link to="/privacy" data-testid="footer-privacy">Privacy</Link> · <Link to="/help" data-testid="footer-help">{t("nav.help")}</Link> · <a href="/api/docs" data-testid="footer-api" target="_blank" rel="noopener noreferrer">API docs</a></div><p>{t("shell.independent")}</p></footer>;
}
