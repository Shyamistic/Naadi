import { useEffect, useMemo, useRef, useState } from "react";
import MapView from "./MapView";
import SamayChakra from "./SamayChakra";
import { accuracy, health, planJourney, searchStops, speedCells, vehicles, type BusLeg, type Cell, type JourneyResponse, type Option, type Place } from "./api";
import { t, type Lang } from "./i18n";

const hhmm = (iso: string) => iso.slice(11, 16);
const istNow = () => new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);
const istHour = () => istNow().getHours();

function PlaceBox({ label, value, onPick, lang, dot }: { label: string; value: Place | null; onPick: (p: Place) => void; lang: Lang; dot: string }) {
  const [q, setQ] = useState(value?.name ?? "");
  const [res, setRes] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => { setQ(value?.name ?? ""); }, [value]);
  const change = (s: string) => {
    setQ(s); setOpen(true);
    window.clearTimeout(timer.current);
    if (s.trim().length < 2) { setRes([]); return; }
    timer.current = window.setTimeout(() => searchStops(s).then((r) => setRes(r.results)).catch(() => setRes([])), 180);
  };
  const locate = () => navigator.geolocation?.getCurrentPosition((g) => {
    const p = { name: t("myLoc", lang), lat: g.coords.latitude, lon: g.coords.longitude };
    onPick(p); setQ(p.name); setOpen(false);
  });
  return (
    <div className="place">
      <span className={`dot ${dot}`} aria-hidden />
      <label>
        <span className="place-label">{label}</span>
        <input value={q} onChange={(e) => change(e.target.value)} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={lang === "hi" ? "स्टॉप या जगह का नाम" : "Stop or place, e.g. Kashmere Gate"} autoComplete="off" />
      </label>
      {dot === "from" && <button className="ghost" onClick={locate} title={t("myLoc", lang)}>◎</button>}
      {open && res.length > 0 && (
        <ul className="suggest" role="listbox">
          {res.map((r) => (
            <li key={`${r.name}-${r.lat}`} onMouseDown={() => { onPick(r); setQ(r.name); setOpen(false); }}>
              <span>{r.name}</span><small>{r.routes} {lang === "hi" ? "रूट" : "routes"}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Badge({ live, lang }: { live: boolean; lang: Lang }) {
  return <span className={`badge ${live ? "live" : "hist"}`}>{live ? `● ${t("live", lang)}` : t("history", lang)}</span>;
}

function Card({ o, active, onClick, lang }: { o: Option; active: boolean; onClick: () => void; lang: Lang }) {
  const bus = o.legs.filter((l): l is BusLeg => l.type === "bus");
  return (
    <button className={`card ${active ? "active" : ""}`} onClick={onClick}>
      <div className="card-top">
        <div className="labels">{o.labels.map((l) => <span key={l} className={`label ${l}`}>{t(l as any, lang)}</span>)}</div>
        <Badge live={o.live} lang={lang} />
      </div>
      <div className="card-main">
        <div className="big">{Math.round(o.total_min)}<small> {t("min", lang)}</small></div>
        <div className="when">
          <div>{t("arrive", lang)} <b>{hhmm(o.arrive)}</b></div>
          {o.range_min && <div className="muted">{t("usually", lang)} {o.range_min[0]}–{o.range_min[1]} {t("min", lang)}</div>}
        </div>
      </div>
      <div className="chips">
        {bus.map((l, i) => (
          <span key={i} className="chip">
            <b>{l.route}</b>{l.also.length > 0 && <em> {t("or", lang)} {l.also.slice(0, 2).join(", ")}</em>}
          </span>
        ))}
        <span className="muted">· {o.transfers} {t("transfers", lang)} · {t("walk", lang)} {Math.round(o.walk_m)} m · ₹{o.fare_inr.non_ac}–{o.fare_inr.ac}</span>
      </div>
      {o.quiet_hour && (
        <div className="compare">
          <span>{t("quiet", lang)} ({String(o.quiet_hour.hour).padStart(2, "0")}:00): <b>{Math.round(o.quiet_hour.total_min)} {t("min", lang)}</b></span>
          {o.timetable_min != null && <span className="muted"> · {t("timetable", lang)} {Math.round(o.timetable_min)}</span>}
        </div>
      )}
    </button>
  );
}

function Detail({ o, lang, hour }: { o: Option; lang: Lang; hour: number }) {
  return (
    <div className="detail">
      <SamayChakra values={o.samay_chakra} current={hour} lang={lang} />
      <p className="chakra-title">{t("chakra", lang)}</p>
      <ol className="timeline">
        {o.legs.map((l, i) => l.type === "walk" ? (
          <li key={i} className="tl walk"><span className="tl-ico">🚶</span>
            <div>{t("walk", lang)} {Math.round(l.metres)} m · {Math.round(l.minutes)} {t("min", lang)}</div></li>
        ) : (
          <li key={i} className="tl bus"><span className="tl-ico route">{l.route}</span>
            <div>
              <div className="tl-head">{t("board", lang)} <b>{l.board.name}</b> <span className="muted">→ {l.towards}</span></div>
              <div className="muted">
                {t("wait", lang)} ~{Math.round(l.wait_min)} {t("min", lang)}{l.wait_source === "live bus" ? ` (${t("live", lang)})` : ""}
                {l.also.length > 0 && <> · {t("or", lang)} {l.also.join(", ")}</>}
              </div>
              {l.next_buses_min.length > 0 && <div className="next">{t("nextBus", lang)}: {l.next_buses_min.map((m) => `${Math.max(0, Math.round(m))}′`).join(" · ")}</div>}
              <div>{t("ride", lang)} {Math.round(l.ride_min)} {t("min", lang)} · {l.stops} {t("stops", lang)} · {l.distance_km} km
                <span className="muted"> · {l.history_samples.toLocaleString()} {lang === "hi" ? "पिछली यात्राओं पर आधारित" : "past trips behind this"}</span></div>
              <div className="tl-head">{t("alight", lang)} <b>{l.alight.name}</b> <span className="muted">{hhmm(l.alight.time)}</span></div>
              <div className="muted small">{t("fare", lang)} ₹{l.fare_inr.non_ac} (non-AC) / ₹{l.fare_inr.ac} (AC) · {t("free", lang)}</div>
            </div></li>
        ))}
      </ol>
    </div>
  );
}

function Accuracy({ lang, onClose }: { lang: Lang; onClose: () => void }) {
  const [a, setA] = useState<any>(null);
  useEffect(() => { accuracy().then(setA).catch(() => setA({})); }, []);
  const rows: [string, number][] = a?.eta?.rows ?? [];
  const max = Math.max(1, ...rows.map((r) => r[1]));
  return (
    <div className="modal" role="dialog" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h2>{lang === "hi" ? "हम कितने सही हैं" : "How accurate is Naadi?"}</h2>
        {!a ? <p>…</p> : rows.length === 0 ? <p className="muted">{lang === "hi" ? "परिणाम जल्द।" : "Results are being computed."}</p> : (
          <>
            <p className="muted">{a.eta.caption}</p>
            <div className="bars">
              {rows.map(([name, v]) => (
                <div key={name} className={`bar ${name.startsWith("Naadi") ? "ours" : ""}`}>
                  <span className="bar-name">{name}</span>
                  <span className="bar-track"><span style={{ width: `${(100 * v) / max}%` }} /></span>
                  <span className="bar-val">{v.toFixed(0)} s</span>
                </div>
              ))}
            </div>
            {(a.journeys?.lines ?? []).map((s: string) => <p key={s}>{s}</p>)}
          </>
        )}
        <button className="primary" onClick={onClose}>OK</button>
      </div>
    </div>
  );
}

export default function App() {
  const [lang, setLang] = useState<Lang>("en");
  const [from, setFrom] = useState<Place | null>({ name: "GGS University ISBT Kashmere Gate", lat: 28.665476, lon: 77.230173 });
  const [to, setTo] = useState<Place | null>({ name: "Nehru Place Terminal", lat: 28.5487, lon: 77.256981 });
  const [when, setWhen] = useState<string>("now");
  const [res, setRes] = useState<JourneyResponse | null>(null);
  const [sel, setSel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [buses, setBuses] = useState<[string, string, number, number, number][]>([]);
  const [showBuses, setShowBuses] = useState(true);
  const [showSpeeds, setShowSpeeds] = useState(false);
  const [cells, setCells] = useState<Cell[] | null>(null);
  const [hour, setHour] = useState(istHour());
  const [weekend, setWeekend] = useState([0, 6].includes(istNow().getDay()));
  const [liveInfo, setLiveInfo] = useState<{ buses: number } | null>(null);
  const [showAcc, setShowAcc] = useState(false);

  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  useEffect(() => {
    const load = () => vehicles().then((v) => setBuses(v.vehicles)).catch(() => {});
    load(); const id = window.setInterval(load, 12000);
    health().then((h) => setLiveInfo(h.live)).catch(() => {});
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => { if (showSpeeds && !cells) speedCells().then((c) => setCells(c.cells)).catch(() => {}); }, [showSpeeds, cells]);

  const go = async () => {
    if (!from || !to) return;
    setBusy(true); setErr(null);
    try {
      const r = await planJourney(`${from.lat},${from.lon}`, `${to.lat},${to.lon}`, when);
      setRes(r); setSel(0);
      if (when !== "now") setHour(Number(when.slice(11, 13)));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const opt = res?.options[sel] ?? null;
  const qHour = useMemo(() => (res ? Number(res.query.depart.slice(11, 13)) : istHour()), [res]);

  return (
    <div className="app">
      <MapView option={opt} others={res?.options ?? []} buses={buses} cells={cells} hour={hour} weekend={weekend}
        showSpeeds={showSpeeds} showBuses={showBuses} from={from ? [from.lat, from.lon] : null} to={to ? [to.lat, to.lon] : null} />
      <header className="brand">
        <img src="/chakra.svg" alt="" className="logo" />
        <div><h1>Naadi <span className="dev">नाड़ी</span></h1><p>{t("tagline", lang)}</p></div>
        <div className="brand-right">
          <button className="ghost" onClick={() => setShowAcc(true)}>{t("accuracy", lang)}</button>
          <button className="ghost" onClick={() => setLang(lang === "en" ? "hi" : "en")}>{lang === "en" ? "हिंदी" : "English"}</button>
        </div>
      </header>
      <aside className="panel">
        <p className="sub">{t("sub", lang)}</p>
        <div className="form">
          <PlaceBox label={t("from", lang)} value={from} onPick={setFrom} lang={lang} dot="from" />
          <button className="swap" onClick={() => { setFrom(to); setTo(from); }} aria-label="swap">⇅</button>
          <PlaceBox label={t("to", lang)} value={to} onPick={setTo} lang={lang} dot="to" />
          <div className="when-row">
            <span className="place-label">{t("leave", lang)}</span>
            <button className={`pill ${when === "now" ? "on" : ""}`} onClick={() => setWhen("now")}>{t("now", lang)}</button>
            <input type="datetime-local" value={when === "now" ? "" : when} onChange={(e) => setWhen(e.target.value || "now")} />
          </div>
          <button className="primary" onClick={go} disabled={busy || !from || !to}>{busy ? "…" : t("plan", lang)}</button>
        </div>
        {err && <p className="error">{err}</p>}
        {res && res.options.length === 0 && <p className="muted">{t("noResults", lang)}</p>}
        <div className="cards">
          {res?.options.map((o, i) => <Card key={i} o={o} active={i === sel} onClick={() => setSel(i)} lang={lang} />)}
        </div>
        {opt && <Detail o={opt} lang={lang} hour={qHour} />}
        <footer className="attr">{t("attribution", lang)}<br /><span className="muted small">{res?.model}</span></footer>
      </aside>
      <div className="layers">
        <label><input type="checkbox" checked={showBuses} onChange={(e) => setShowBuses(e.target.checked)} /> {t("liveBuses", lang)}
          {liveInfo && <span className="muted"> {buses.length.toLocaleString()}</span>}</label>
        <label><input type="checkbox" checked={showSpeeds} onChange={(e) => setShowSpeeds(e.target.checked)} /> {t("speeds", lang)}</label>
        {showSpeeds && (
          <div className="slider">
            <input type="range" min={0} max={23} value={hour} onChange={(e) => setHour(Number(e.target.value))} />
            <span>{String(hour).padStart(2, "0")}:00</span>
            <button className={`pill ${!weekend ? "on" : ""}`} onClick={() => setWeekend(false)}>{t("weekday", lang)}</button>
            <button className={`pill ${weekend ? "on" : ""}`} onClick={() => setWeekend(true)}>{t("weekend", lang)}</button>
            <div className="legend"><span className="lg slow" />{lang === "hi" ? "धीमा" : "slow"}<span className="lg fast" />{lang === "hi" ? "तेज़" : "fast"}</div>
          </div>
        )}
      </div>
      {showAcc && <Accuracy lang={lang} onClose={() => setShowAcc(false)} />}
    </div>
  );
}
