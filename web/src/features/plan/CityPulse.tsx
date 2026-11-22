import { usePulse } from "../../api/queries";
import { useT } from "../../i18n/I18nProvider";
import { fmtCount } from "../../i18n/format";
import "./pulse.css";

// "Delhi right now": the live traffic model in one card. Every bus is a moving sensor: the server compares the
// stretches buses drove in the last ~20 minutes with October's history for the same hour (GET /pulse).
// The card is absent (not an error) when the server or feed can't provide it.
const mid = (c: [[number, number], [number, number]]): [number, number] => [(c[0][0] + c[1][0]) / 2, (c[0][1] + c[1][1]) / 2];

export function CityPulse({ onFocus }: { onFocus?: (center: [number, number]) => void }) {
  const { t } = useT();
  const query = usePulse();
  const pulse = query.data;
  if (query.isPending) return <section className="pulse-card is-loading" aria-busy="true" data-testid="pulse-loading"><div className="pulse-skeleton" /><div className="pulse-skeleton short" /></section>;
  if (!pulse || query.isError) return null;
  const vs = pulse.vs_usual;
  const hour = pulse.hour == null ? "" : `${String(pulse.hour).padStart(2, "0")}:00`;
  const daytype = t(pulse.day_type === "weekend" ? "pulse.weekend" : "pulse.weekday");
  const trend = !vs ? null : Math.abs(vs.pct) < 3 ? t("pulse.usual") : vs.pct > 0 ? t("pulse.slower", { pct: vs.pct }) : t("pulse.faster", { pct: -vs.pct });
  const tone = !vs || Math.abs(vs.pct) < 3 ? "usual" : vs.pct > 0 ? "slower" : "faster";
  const time = pulse.feed_time ? pulse.feed_time.slice(11, 16) : "";
  return <section className="pulse-card" aria-labelledby="pulse-title" data-testid="city-pulse">
    <header><span className={`pulse-dot ${pulse.stale ? "stale" : ""}`} aria-hidden="true" /><h2 id="pulse-title">{t("pulse.title")}</h2>{time && <span className="pulse-time">{time}</span>}</header>
    {pulse.stale ? <p className="pulse-note">{t("pulse.stale")}</p> : <>
      <div className="pulse-stats">
        <div className="pulse-stat"><b data-testid="pulse-buses">{fmtCount(pulse.buses)}</b><span>{t("pulse.buses")}</span></div>
        {trend && <div className={`pulse-stat ${tone}`}><b data-testid="pulse-trend">{trend}</b><span>{t("pulse.vsUsual", { daytype, hour })}</span></div>}
      </div>
      {pulse.slow.length > 0 && <><h3>{t("pulse.slowTitle")}</h3><ol className="pulse-slow">{pulse.slow.slice(0, 3).map((stretch, index) => <li key={`${stretch.from}-${stretch.to}`}>
        <button type="button" data-testid={`pulse-slow-${index}`} onClick={() => onFocus?.(mid(stretch.coords))}>
          <span className="pulse-slow-name">{stretch.from} → {stretch.to}</span>
          <small>{t("pulse.slowDetail", { ratio: stretch.ratio.toFixed(1), buses: stretch.buses })}{stretch.routes.length ? ` · ${stretch.routes.join(", ")}` : ""}</small>
        </button></li>)}</ol></>}
      <p className="pulse-note">{t("pulse.note", { n: fmtCount(pulse.traversals), min: pulse.window_min })}</p>
    </>}
  </section>;
}
