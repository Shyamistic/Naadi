import { useEffect, useState } from "react";
import { apiPausedUntil, onApiPause } from "../api/client";
import { useT } from "../i18n/I18nProvider";
import "./status.css";

// While the server has asked the app to slow down (HTTP 429), requests wait and then carry on by themselves.
// This says why the page is paused and for how long, so nobody reloads it.
function BusyBanner() {
  const { t } = useT();
  const [until, setUntil] = useState(apiPausedUntil);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => onApiPause((next) => { setUntil(next); setNow(Date.now()); }), []);
  useEffect(() => {
    if (until <= Date.now()) return;
    const timer = window.setInterval(() => { const current = Date.now(); setNow(current); if (current >= until) window.clearInterval(timer); }, 500);
    return () => window.clearInterval(timer);
  }, [until]);
  const seconds = Math.ceil((until - now) / 1000);
  if (seconds <= 0) return null;
  return <div className="status-banner" role="status" aria-live="polite" data-testid="api-busy">{t("shell.busy", { s: seconds })}</div>;
}

// Short confirmations ("Link copied") sent by any screen as a `naadi-toast` window event.
function Toasts() {
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    let timer = 0;
    const show = (event: Event) => { const text = (event as CustomEvent<unknown>).detail; if (typeof text !== "string" || !text) return; setMessage(text); window.clearTimeout(timer); timer = window.setTimeout(() => setMessage(null), 3000); };
    window.addEventListener("naadi-toast", show);
    return () => { window.removeEventListener("naadi-toast", show); window.clearTimeout(timer); };
  }, []);
  if (!message) return null;
  return <div className="status-toast" role="status" aria-live="polite" data-testid="toast">{message}</div>;
}

export function StatusMessages() { return <><BusyBanner /><Toasts /></>; }
