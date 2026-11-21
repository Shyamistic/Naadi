import { useEffect } from "react";
import { Outlet, useLocation } from "react-router";
import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { MapHost } from "../map/MapHost";
import { Sheet } from "../components/Sheet";
import { hideSplash, markAppStarted, MAP_SPLASH_CAP_MS } from "./splash";
import css from "./shell.module.css";
import "./sheet.css";

const DOCUMENT_PATHS = ["/accuracy", "/about", "/privacy", "/accessibility", "/terms", "/help", "/settings"];

export function AppShell() {
  const location = useLocation();
  const documentPage = DOCUMENT_PATHS.some((path) => location.pathname.startsWith(path));
  useEffect(() => {
    markAppStarted();
    // Document pages have no map, so nothing else would hide the splash. Map pages give the map a few seconds to
    // draw (MapHost hides the splash once it's ready), but a slow or broken map must never block the page.
    if (documentPage) {
      hideSplash();
      return;
    }
    const timer = window.setTimeout(hideSplash, MAP_SPLASH_CAP_MS);
    return () => window.clearTimeout(timer);
  }, [documentPage]);
  return <div className={`${css.shell} shell`}><a href="#main" className="skip-link" data-testid="skip-link">Skip to main content</a><AppHeader /><main className="app-content" id="main">{!documentPage ? <div className="map-area"><MapHost><Sheet><section className="panel"><div className="panel-inner"><Outlet /></div></section></Sheet></MapHost></div> : <section className="panel document-panel"><div className="panel-inner"><Outlet /><Footer /></div></section>}</main></div>;
}
