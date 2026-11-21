import { Component, useEffect, type ErrorInfo, type ReactNode } from "react";
import { useRouteError } from "react-router";
import { hideSplash } from "../app/splash";
import { useT } from "../i18n/I18nProvider";

// Last-resort boundary around the router. It also hides the boot splash, so the message is never covered.
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false };
  static getDerivedStateFromError() { return { error: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.warn("[app] render error", error.message, info.componentStack); hideSplash(); }
  render() {
    if (this.state.error) return <div className="state" role="alert"><h1>Something went wrong</h1><p>Try reloading Naadi.</p><button className="ui-button primary" data-testid="error-reload" onClick={() => location.reload()}>Reload</button><a href="/" data-testid="error-home">Home</a></div>;
    return this.props.children;
  }
}

// The router shows this when a page fails to load or render, for example when its code can't be fetched.
export function RouteError() {
  const error = useRouteError();
  const { t } = useT();
  useEffect(() => { console.warn("[app] page error", error); hideSplash(); }, [error]);
  return <div className="state" role="alert" data-testid="route-error"><h1>{t("pages.error")}</h1><p>{t("pages.errorText")}</p><button className="ui-button primary" data-testid="route-error-reload" onClick={() => location.reload()}>{t("pages.reload")}</button> <a href="/" data-testid="route-error-home">{t("pages.planJourney")}</a></div>;
}
