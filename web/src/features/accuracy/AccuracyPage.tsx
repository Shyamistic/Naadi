import { useMemo, useState, type ReactNode } from "react";
import { useAccuracy } from "../../api/queries";
import { API_BASE } from "../../api/client";
import { useT } from "../../i18n/I18nProvider";
import type { Lang, TranslationKey, TranslationVars } from "../../i18n";
import css from "./accuracy.module.css";

// The page reads validation/results/summary.json (GET /accuracy). Every section is optional: a section that is
// missing or malformed is skipped, and the raw figures stay available under "All published figures".

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
const at = (v: unknown, ...path: string[]): unknown => path.reduce<unknown>((cur, key) => (isObj(cur) ? cur[key] : undefined), v);
const join = (parts: (string | undefined)[]) => parts.filter(Boolean).join(" · ") || undefined;

const REPORT_URL = "https://github.com/Shyamistic/Naadi/blob/main/docs/VALIDATION_REPORT.md";
const ETA_METHODS: Record<string, TranslationKey> = {
  naadi: "accuracy.m.naadi", live_only: "accuracy.m.live_only", lnkf: "accuracy.m.lnkf", gbm: "accuracy.m.gbm", eb: "accuracy.m.eb",
  ha: "accuracy.m.ha", city: "accuracy.m.city", timetable: "accuracy.m.timetable", persist: "accuracy.m.persist",
};
// Labels that older results files used instead of method codes ("Naadi history" was history + live).
const ETA_LEGACY: Record<string, string> = { "Official timetable": "timetable", "Naadi history": "naadi" };
// Planner code, its label, and its key in the "intervals" section.
const PLANNERS: [string, TranslationKey, string][] = [
  ["naadi_live", "accuracy.p.naadiLive", "live"], ["naadi_nowcast", "accuracy.p.naadiNowcast", "naadi_nowcast"],
  ["naadi", "accuracy.p.naadi", "history"], ["timetable", "accuracy.p.timetable", "timetable"],
];
const CALC_METHODS: [string, TranslationKey][] = [
  ["Naadi history + live", "accuracy.p.naadiLive"], ["Naadi history", "accuracy.p.naadi"], ["ETA Calculator (Transport Stack)", "accuracy.c.calc"],
];

type Fmt = ReturnType<typeof makeFormat>;
function makeFormat(lang: Lang, t: (key: TranslationKey, vars?: TranslationVars) => string) {
  const locale = lang === "hi" ? "hi-IN" : "en-IN";
  const fixed = (v: number, digits: number) => new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
  const day = new Intl.DateTimeFormat(locale, { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" });
  const stamp = new Intl.DateTimeFormat(locale, { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
  return {
    t,
    count: (v: number) => new Intl.NumberFormat(locale).format(Math.round(v)),
    min: (v: number, digits = 1) => t("accuracy.unitMin", { v: fixed(v, digits) }),
    sec: (v: number, digits = 1) => t("accuracy.unitSec", { v: fixed(v, digits) }),
    pct: (v: number, digits = 1) => `${fixed(v, digits)}%`,
    stamp: (iso: string) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? iso : stamp.format(d); },
    days: (list: unknown) => {
      if (!Array.isArray(list)) return undefined;
      const dates = list.map((d) => new Date(`${String(d).replaceAll("_", "-")}T12:00:00+05:30`)).filter((d) => !Number.isNaN(d.getTime())).sort((a, b) => a.getTime() - b.getTime());
      if (!dates.length) return undefined;
      const range = (() => { try { return day.formatRange(dates[0], dates[dates.length - 1]); } catch { return `${day.format(dates[0])} – ${day.format(dates[dates.length - 1])}`; } })();
      return t("accuracy.testDays", { days: range });
    },
  };
}

function etaRows(eta: unknown) {
  const rows = at(eta, "rows");
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row) => {
    if (!Array.isArray(row) || typeof row[0] !== "string") return [];
    const mae = num(row[1]);
    return mae === undefined ? [] : [{ code: ETA_LEGACY[row[0]] ?? row[0], mae }];
  }).sort((a, b) => a.mae - b.mae);
}
function etaName(code: string, eta: unknown, t: Fmt["t"]) {
  const key = ETA_METHODS[code];
  if (key) return t(key);
  const label = at(eta, "labels", code);
  return typeof label === "string" ? label : code;
}
// A 95% interval of a difference, as positive magnitudes in ascending order.
function magnitudes(ci: unknown): [number, number] | undefined {
  if (!Array.isArray(ci) || ci.length !== 2) return undefined;
  const lo = num(ci[0]); const hi = num(ci[1]);
  if (lo === undefined || hi === undefined) return undefined;
  const a = Math.abs(lo); const b = Math.abs(hi);
  return a < b ? [a, b] : [b, a];
}

type Row = { key: string; cells: ReactNode[]; highlight?: boolean };
function Table({ head, rows, className }: { head: string[]; rows: Row[]; className?: string }) {
  return <div className={css.tableWrap}><table className={`${css.table} ${className ?? ""}`}><thead><tr>{head.map((h, i) => <th key={i} scope="col">{h}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.key} className={row.highlight ? css.highlight : undefined}>{row.cells.map((cell, i) => i === 0 ? <th key={i} scope="row">{cell}</th> : <td key={i}>{cell}</td>)}</tr>)}</tbody></table></div>;
}
function ValueBar({ text, value, max }: { text: string; value: number; max: number }) {
  return <span className={css.valueBar}><span>{text}</span><span className={css.bar} aria-hidden="true"><i style={{ width: `${Math.max(2, Math.min(100, (value / max) * 100))}%` }} /></span></span>;
}
function Card({ id, title, note, children }: { id: string; title: string; note?: string; children: ReactNode }) {
  return <section className={css.card} aria-labelledby={`${id}-title`} data-testid={`accuracy-${id}`}><h2 id={`${id}-title`}>{title}</h2>{note && <p className={css.note}>{note}</p>}{children}</section>;
}
function Sample({ text }: { text?: string }) { return text ? <p className={css.sample}>{text}</p> : null; }

type Tile = { id: string; label: string; value: string; note: string; compare?: string; sample?: string };
function headlineTiles(s: Obj, f: Fmt): Tile[] {
  const { t } = f;
  const tiles: Tile[] = [];
  const eta = etaRows(s.eta);
  const naadi = eta.find((r) => r.code === "naadi");
  const timetable = eta.find((r) => r.code === "timetable");
  const etaN = num(at(s.eta, "n"));
  if (naadi) tiles.push({ id: "eta", label: t("accuracy.tileEta"), value: f.min(naadi.mae / 60), note: t("accuracy.meanError"),
    compare: timetable ? t("accuracy.vs", { name: t("accuracy.m.timetable"), value: f.min(timetable.mae / 60) }) : undefined,
    sample: join([etaN !== undefined ? t("accuracy.samplePredictions", { n: f.count(etaN) }) : undefined, f.days(at(s.eta, "test_days"))]) });
  const ride = at(s.rides, "with_gaps_over_10min");
  const rideErr = num(at(ride, "mean_error_min")); const rideLen = num(at(ride, "mean_ride_min")); const rideN = num(at(ride, "n")); const ride10 = num(at(ride, "within_10min_pct"));
  if (rideErr !== undefined && rideLen) tiles.push({ id: "rides", label: t("accuracy.tileRides"), value: f.min(rideErr), note: t("accuracy.ofRide", { share: f.pct((rideErr / rideLen) * 100), ride: f.min(rideLen, 0) }),
    compare: ride10 !== undefined ? t("accuracy.within10Share", { v: f.pct(ride10) }) : undefined,
    sample: join([rideN !== undefined ? t("accuracy.sampleRides", { n: f.count(rideN) }) : undefined, f.days(at(s.rides, "test_days"))]) });
  const door = at(s.journeys, "report", "naadi_live", "calibrated") ?? at(s.journeys, "report", "naadi", "calibrated");
  const doorErr = num(at(door, "mae_min")); const doorN = num(at(door, "n")); const doorTt = num(at(s.journeys, "report", "timetable", "calibrated", "mae_min"));
  if (doorErr !== undefined) tiles.push({ id: "journeys", label: t("accuracy.tileJourneys"), value: f.min(doorErr), note: t("accuracy.meanError"),
    compare: doorTt !== undefined ? t("accuracy.vs", { name: t("accuracy.p.timetable"), value: f.min(doorTt) }) : undefined,
    sample: join([doorN !== undefined ? t("accuracy.sampleJourneys", { n: f.count(doorN) }) : undefined, f.days(at(s.journeys, "test_days"))]) });
  const gNaadi = num(at(s.google, "naadi", "mae_min")); const gGoogle = num(at(s.google, "google", "mae_min")); const gN = num(at(s.google, "both_replayed"));
  if (gNaadi !== undefined) tiles.push({ id: "google", label: t("accuracy.tileGoogle"), value: f.min(gNaadi), note: t("accuracy.meanError"),
    compare: gGoogle !== undefined ? t("accuracy.vs", { name: t("accuracy.googleName"), value: f.min(gGoogle) }) : undefined,
    sample: join([gN !== undefined ? t("accuracy.sampleTrips", { n: f.count(gN) }) : undefined, f.days(at(s.google, "days"))]) });
  const cNaadi = num(at(s.eta_calculator, "methods", "Naadi history + live", "mae_min")); const cCalc = num(at(s.eta_calculator, "methods", "ETA Calculator (Transport Stack)", "mae_min")); const cN = num(at(s.eta_calculator, "n"));
  if (cNaadi !== undefined) tiles.push({ id: "calculator", label: t("accuracy.tileCalc"), value: f.min(cNaadi), note: t("accuracy.meanError"),
    compare: cCalc !== undefined ? t("accuracy.vs", { name: t("accuracy.c.calc"), value: f.min(cCalc) }) : undefined,
    sample: join([cN !== undefined ? t("accuracy.sampleAnswers", { n: f.count(cN) }) : undefined, f.days(at(s.eta_calculator, "days"))]) });
  return tiles;
}

function EtaSection({ eta, f }: { eta: unknown; f: Fmt }) {
  const { t } = f;
  const rows = etaRows(eta);
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => r.mae));
  const within = num(at(eta, "naadi", "within_2min_pct"));
  const bias = num(at(eta, "naadi", "bias_s"));
  const best = at(eta, "best_baseline");
  const diff = num(at(eta, "significance", "diff_mae_s"));
  const ci = magnitudes(at(eta, "significance", "ci95"));
  const bands = at(eta, "by_band");
  const n = num(at(eta, "n"));
  return <Card id="eta" title={t("accuracy.etaTitle")} note={t("accuracy.etaNote")}>
    <Table head={[t("accuracy.colMethod"), t("accuracy.colMeanError")]} rows={rows.map((r) => ({ key: r.code, highlight: r.code === "naadi", cells: [etaName(r.code, eta, t), <ValueBar text={f.sec(r.mae)} value={r.mae} max={max} />] }))} />
    {(within !== undefined || bias !== undefined) && <p className={css.small}>{within !== undefined && t("accuracy.etaStats", { within: f.pct(within) })} {bias !== undefined && t(bias < 0 ? "accuracy.biasEarly" : "accuracy.biasLate", { v: f.sec(Math.abs(bias)) })}</p>}
    {typeof best === "string" && diff !== undefined && diff < 0 && ci && <p className={css.small}>{t("accuracy.etaLead", { name: etaName(best, eta, t), diff: f.sec(Math.abs(diff)), lo: f.sec(ci[0]), hi: f.sec(ci[1]) })}</p>}
    {isObj(bands) && Object.keys(bands).length > 0 && <>
      <h3>{t("accuracy.etaBands")}</h3>
      <Table head={[t("accuracy.colAhead"), t("accuracy.m.naadi"), t("accuracy.m.timetable")]} rows={Object.entries(bands).map(([band, v]) => {
        const a = num(at(v, "naadi")); const b = num(at(v, "timetable"));
        return { key: band, cells: [t("accuracy.bandStops", { range: band.replace(/\s*stops?$/i, "").replace("-", "–") }), a !== undefined ? f.sec(a) : "—", b !== undefined ? f.sec(b) : "—"] };
      })} />
    </>}
    <Sample text={join([n !== undefined ? t("accuracy.samplePredictions", { n: f.count(n) }) : undefined, f.days(at(eta, "test_days"))])} />
  </Card>;
}

function RidesSection({ rides, f }: { rides: unknown; f: Fmt }) {
  const { t } = f;
  const variants: [string, TranslationKey][] = [["with_gaps_over_10min", "accuracy.ridesAll"], ["without_gaps_over_10min", "accuracy.ridesNoGap"]];
  const rows: Row[] = variants.flatMap(([key, label]) => {
    const r = at(rides, key);
    const err = num(at(r, "mean_error_min")); const len = num(at(r, "mean_ride_min")); const n = num(at(r, "n"));
    if (err === undefined || !len) return [];
    const w5 = num(at(r, "within_5min_pct")); const w10 = num(at(r, "within_10min_pct"));
    return [{ key, highlight: key === "with_gaps_over_10min", cells: [n !== undefined ? `${t(label)} (${f.count(n)})` : t(label), f.min(len), f.min(err, 2), f.pct((err / len) * 100), w5 !== undefined ? f.pct(w5) : "—", w10 !== undefined ? f.pct(w10) : "—"] }];
  });
  if (!rows.length) return null;
  return <Card id="rides" title={t("accuracy.ridesTitle")} note={t("accuracy.ridesNote")}>
    <Table head={[t("accuracy.colRides"), t("accuracy.colMeanRide"), t("accuracy.colMeanError"), t("accuracy.colShare"), t("accuracy.colWithin5"), t("accuracy.colWithin10")]} rows={rows} />
    <Sample text={f.days(at(rides, "test_days"))} />
  </Card>;
}

function JourneysSection({ journeys, intervals, f }: { journeys: unknown; intervals: unknown; f: Fmt }) {
  const { t } = f;
  const report = at(journeys, "report");
  const stats = PLANNERS.flatMap(([code, label]) => {
    const c = at(report, code, "calibrated"); const mae = num(at(c, "mae_min"));
    return mae === undefined ? [] : [{ code, label, mae, c }];
  });
  if (!stats.length) return null;
  const max = Math.max(...stats.map((s) => s.mae));
  const ranges: Row[] = PLANNERS.flatMap(([code, label, key]) => {
    const cover = num(at(intervals, key, "test_coverage")); const width = num(at(intervals, key, "median_width_min"));
    return cover === undefined ? [] : [{ key: code, highlight: code === "naadi_live", cells: [t(label), f.pct(cover * 100, 0), width !== undefined ? f.min(width, 0) : "—"] }];
  });
  const liveSlots = at(report, "naadi_live", "by_slot_mae_min"); const ttSlots = at(report, "timetable", "by_slot_mae_min");
  return <Card id="journeys" title={t("accuracy.journeysTitle")} note={t("accuracy.journeysNote")}>
    <Table head={[t("accuracy.colPlanner"), t("accuracy.colJourneys"), t("accuracy.colMeanError"), t("accuracy.colMedianError"), t("accuracy.colWithin10")]} rows={stats.map(({ code, label, mae, c }) => {
      const n = num(at(c, "n")); const median = num(at(c, "median_abs_min")); const w10 = num(at(c, "within_10min_pct"));
      return { key: code, highlight: code === "naadi_live", cells: [t(label), n !== undefined ? f.count(n) : "—", <ValueBar text={f.min(mae)} value={mae} max={max} />, median !== undefined ? f.min(median) : "—", w10 !== undefined ? f.pct(w10, 0) : "—"] };
    })} />
    <p className={css.small}>{t("accuracy.liveExplained")}</p>
    {at(journeys, "walking") === "straight_line" && <p className={css.caveat} data-testid="accuracy-walk-caveat">{t("accuracy.walkCaveat")}</p>}
    {ranges.length > 0 && <>
      <h3>{t("accuracy.intervalsTitle")}</h3>
      <p className={css.small}>{t("accuracy.intervalsNote")}</p>
      <Table head={[t("accuracy.colPlanner"), t("accuracy.colCoverage"), t("accuracy.colWidth")]} rows={ranges} />
    </>}
    {isObj(liveSlots) && Object.keys(liveSlots).length > 0 && <>
      <h3>{t("accuracy.bySlot")}</h3>
      <Table head={[t("accuracy.colLeaving"), t("accuracy.p.naadiLive"), t("accuracy.p.timetable")]} rows={Object.keys(liveSlots).sort().map((slot) => {
        const a = num(liveSlots[slot]); const b = num(at(ttSlots, slot));
        return { key: slot, cells: [slot, a !== undefined ? f.min(a) : "—", b !== undefined ? f.min(b) : "—"] };
      })} />
    </>}
    <Sample text={f.days(at(journeys, "test_days"))} />
  </Card>;
}

function CalculatorSection({ calc, f }: { calc: unknown; f: Fmt }) {
  const { t } = f;
  const rows: Row[] = CALC_METHODS.flatMap(([name, label]) => {
    const m = at(calc, "methods", name); const mae = num(at(m, "mae_min"));
    if (mae === undefined) return [];
    const median = num(at(m, "median_abs_min")); const w2 = num(at(m, "within_2min_pct"));
    return [{ key: name, highlight: name === "Naadi history + live", cells: [t(label), f.min(mae, 2), median !== undefined ? f.min(median, 2) : "—", w2 !== undefined ? f.pct(w2, 0) : "—"] }];
  });
  if (!rows.length) return null;
  const asServed = at(calc, "headline_variant") === "same_fix" ? num(at(calc, "variants", "as_served", "methods", "Naadi history + live", "mae_min")) : undefined;
  const fixAge = num(at(calc, "notes", "median_fix_age_s"));
  const n = num(at(calc, "n"));
  return <Card id="calculator" title={t("accuracy.etaCalculatorTitle")} note={t("accuracy.etaCalculatorNote")}>
    <Table head={[t("accuracy.colMethod"), t("accuracy.colMeanError"), t("accuracy.colMedianError"), t("accuracy.colWithin2")]} rows={rows} />
    {asServed !== undefined && <p className={css.small}>{t("accuracy.calcAsServed", { v: f.min(asServed, 2) })}</p>}
    {fixAge !== undefined && <p className={css.small}>{t("accuracy.calcFixAge", { age: f.min(fixAge / 60) })}</p>}
    <Sample text={join([n !== undefined ? t("accuracy.sampleAnswers", { n: f.count(n) }) : undefined, f.days(at(calc, "days"))])} />
  </Card>;
}

function GoogleSection({ google, f }: { google: unknown; f: Fmt }) {
  const { t } = f;
  const who: [string, string][] = [["naadi", t("accuracy.naadiName")], ["google", t("accuracy.googleName")]];
  const rows: Row[] = who.flatMap(([key, label]) => {
    const mae = num(at(google, key, "mae_min"));
    if (mae === undefined) return [];
    const median = num(at(google, key, "median_abs_min")); const w10 = num(at(google, key, "within_10min_pct"));
    return [{ key, highlight: key === "naadi", cells: [label, f.min(mae), median !== undefined ? f.min(median) : "—", w10 !== undefined ? f.pct(w10, 0) : "—"] }];
  });
  if (!rows.length) return null;
  const diff = num(at(google, "mae_diff_naadi_minus_google_min", "mean"));
  const ciRaw = at(google, "mae_diff_naadi_minus_google_min", "ci95");
  const ci = magnitudes(ciRaw);
  const ciBelowZero = Array.isArray(ciRaw) && ciRaw.every((x) => (num(x) ?? 0) < 0);
  const naadiActual = num(at(google, "actual_time_median_min", "naadi_itinerary")); const googleActual = num(at(google, "actual_time_median_min", "google_itinerary"));
  const n = num(at(google, "both_replayed"));
  return <Card id="google" title={t("accuracy.googleTitle")} note={t("accuracy.googleNote")}>
    <Table head={[t("accuracy.colPlanner"), t("accuracy.colMeanError"), t("accuracy.colMedianError"), t("accuracy.colWithin10")]} rows={rows} />
    {diff !== undefined && diff < 0 && ci && ciBelowZero && <p className={css.small}>{t("accuracy.googleDiff", { diff: f.min(Math.abs(diff)), lo: f.min(ci[0]), hi: f.min(ci[1]) })}</p>}
    {naadiActual !== undefined && googleActual !== undefined && naadiActual < googleActual && <p className={css.small}>{t("accuracy.googleFaster", { naadi: f.min(naadiActual, 0), google: f.min(googleActual, 0) })}</p>}
    {n !== undefined && n < 300 && <p className={css.caveat}>{t("accuracy.smallSample")}</p>}
    <Sample text={join([n !== undefined ? t("accuracy.sampleTrips", { n: f.count(n) }) : undefined, f.days(at(google, "days"))])} />
  </Card>;
}

function label(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase()); }
function scalar(value: unknown): string { if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3); if (typeof value === "boolean") return value ? "Yes" : "No"; if (value === null || value === undefined) return "—"; return String(value); }
function flatten(value: unknown, prefix = "", depth = 0): [string, string][] {
  if (depth > 6) return [[prefix || "Value", scalar(value)]];
  if (Array.isArray(value)) return value.flatMap((item, i) => Array.isArray(item) && item.length === 2 && typeof item[0] === "string" ? flatten(item[1], `${prefix} › ${item[0]}`, depth + 1) : flatten(item, `${prefix} › ${i + 1}`, depth + 1));
  if (isObj(value)) return Object.entries(value).flatMap(([k, v]) => flatten(v, prefix ? `${prefix} › ${label(k)}` : label(k), depth + 1));
  return [[prefix || "Value", scalar(value)]];
}
function Details({ summary, f }: { summary: Obj; f: Fmt }) {
  const { t } = f;
  const [open, setOpen] = useState(false);
  return <details className={css.details} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary data-testid="accuracy-details">{t("accuracy.detailsTitle")}</summary>
    <p className={css.small}>{t("accuracy.detailsNote")}</p>
    <a className={css.download} href={`${API_BASE}/accuracy`} download="naadi-accuracy.json" data-testid="accuracy-download">{t("accuracy.download")}</a>
    {open && <Table className={css.raw} head={[t("accuracy.measure"), t("accuracy.value")]} rows={flatten(summary).map(([key, value], i) => ({ key: `${i}`, cells: [key, value] }))} />}
  </details>;
}

function Loading({ text }: { text: string }) {
  return <div className={css.loading} role="status" aria-busy="true" data-testid="accuracy-loading"><span className="visually-hidden">{text}</span><div className={css.tiles}>{[0, 1, 2, 3].map((i) => <div key={i} className={css.tile} />)}</div><div className={css.skeletonCard} /></div>;
}

export default function AccuracyPage() {
  const { t, lang } = useT();
  const f = useMemo(() => makeFormat(lang, t), [lang, t]);
  const query = useAccuracy();
  const summary = isObj(query.data) ? query.data : undefined;
  const hasResults = summary ? Object.keys(summary).some((key) => key !== "updated") : false;
  const updated = typeof summary?.updated === "string" ? f.stamp(summary.updated) : undefined;
  const tiles = summary && hasResults ? headlineTiles(summary, f) : [];
  return <article className={css.page} data-testid="accuracy-page">
    <header className={css.header}>
      <h1>{t("accuracy.title")}</h1>
      <p className={css.lede}>{t("accuracy.lede")} {t("accuracy.heldOut")}</p>
      {updated && <p className={css.updated} data-testid="accuracy-updated">{t("accuracy.updated", { date: updated })}</p>}
    </header>
    {query.isPending && <Loading text={t("accuracy.loading")} />}
    {!summary && query.isError && <div role="alert" className={css.error} data-testid="accuracy-error"><p>{t("accuracy.loadError")}</p><button type="button" className="ui-button" data-testid="accuracy-retry" onClick={() => void query.refetch()}>{t("accuracy.retry")}</button></div>}
    {summary && !hasResults && <p className={css.empty} data-testid="accuracy-empty">{t("accuracy.empty")}</p>}
    {summary && hasResults && <>
      {tiles.length > 0 && <section className={css.glance} aria-labelledby="glance-title"><h2 id="glance-title">{t("accuracy.glance")}</h2><div className={css.tiles} data-testid="accuracy-tiles">{tiles.map((tile) => <div key={tile.id} className={css.tile} data-testid={`accuracy-tile-${tile.id}`}><h3>{tile.label}</h3><p className={css.tileValue}>{tile.value}</p><p className={css.tileNote}>{tile.note}</p>{tile.compare && <p className={css.tileCompare}>{tile.compare}</p>}<Sample text={tile.sample} /></div>)}</div></section>}
      <div className={css.cards}>
        <EtaSection eta={summary.eta} f={f} />
        <RidesSection rides={summary.rides} f={f} />
        <JourneysSection journeys={summary.journeys} intervals={summary.intervals} f={f} />
        <CalculatorSection calc={summary.eta_calculator} f={f} />
        <GoogleSection google={summary.google} f={f} />
      </div>
      <Details summary={summary} f={f} />
    </>}
    <p className={css.report}><a href={REPORT_URL} target="_blank" rel="noopener noreferrer">{t("accuracy.report")}</a></p>
  </article>;
}
