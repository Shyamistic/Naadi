import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { RouteBadge, Segmented, Button, EmptyState, ErrorState, Skeleton, Banner } from "../../ui/primitives";
import type { Departures, StopsAll } from "../../api/types";
import { copySharePath, getAllStops, getDepartures, getRouteSearch, stopIds } from "./data";
import { StopsOverlay } from "../../map/overlays/stops";
import { useMap } from "../../map/MapContext";
import { useT } from "../../i18n/I18nProvider";
import css from "./stop.module.css";

const timeSince = (date: number) => Math.max(0, Math.floor((Date.now() - date) / 1000));
export default function StopPage() {
  const { ids: rawIds } = useParams(); const navigate = useNavigate(); const ids = stopIds(rawIds);
  const { flyTo } = useMap(); const { t } = useT();
  const [rows, setRows] = useState<Departures[]>([]); const [updated, setUpdated] = useState<number | null>(null); const [seconds, setSeconds] = useState(0); const [loading, setLoading] = useState(true); const [error, setError] = useState(false); const [refreshError, setRefreshError] = useState(false); const [filter, setFilter] = useState("all"); const [stops, setStops] = useState<StopsAll>();
  const load = useCallback(async (initial = false) => { if (!ids) return; if (initial) setLoading(true); try { const response = await Promise.all(ids.map((id) => getDepartures(id))); setRows(response); const now = Date.now(); setUpdated(now); setSeconds(0); setError(false); setRefreshError(false); } catch { if (initial) setError(true); else setRefreshError(true); } finally { if (initial) setLoading(false); } }, [ids]);
  useEffect(() => { void load(true); const poll = window.setInterval(() => void load(false), 30000); const clock = window.setInterval(() => setSeconds(updated ? timeSince(updated) : 0), 5000); return () => { window.clearInterval(poll); window.clearInterval(clock); }; }, [load, updated]);
  useEffect(() => { if (ids) void getAllStops().then(setStops).catch(() => undefined); }, [ids]);
  useEffect(() => { const first = rows[0]; if (first) flyTo([first.lon, first.lat], 16); }, [flyTo, rows]);
  const merged = useMemo(() => { const values = rows.flatMap((response) => response.departures.map((departure) => ({ ...departure, name: response.name, lat: response.lat, lon: response.lon }))); return values.sort((a, b) => (a.live_eta_min?.[0] ?? 999) - (b.live_eta_min?.[0] ?? 999) || (a.typical_wait_min ?? 999) - (b.typical_wait_min ?? 999)); }, [rows]);
  const visible = filter === "live" ? merged.filter((row) => (row.live_eta_min?.length ?? 0) > 0) : merged;
  if (!ids) return <ErrorState title="This stop link is invalid" body="Choose a stop from the planner." action={<Button testId="stop-home" onClick={() => navigate("/")}>Go to planner</Button>} />;
  if (loading) return <div className={css.page}><h1><Skeleton width="65%" /></h1>{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} height="4.5rem" />)}</div>;
  if (error) return <ErrorState title="Couldn't load this stop" body="Try again when the live service is available." action={<Button testId="stop-retry" onClick={() => void load(true)}>Retry</Button>} />;
  if (!rows.length) return <EmptyState title="This stop doesn't exist" action={<Button testId="stop-home" onClick={() => navigate("/")}>Go to planner</Button>} />;
  const first = rows[0]; const path = `/stop/${ids.join(",")}`;
  const plan = (kind: "from" | "to") => navigate(`/?${kind}=${first.lat},${first.lon}&${kind}Name=${encodeURIComponent(first.name)}`);
  const share = () => void copySharePath(path).then(() => window.dispatchEvent(new CustomEvent("naadi-toast", { detail: "Link copied" })));
  const routeFor = async (route: typeof merged[number]) => { if (route.route_id) { navigate(`/route/${route.route_id}`); return; } try { const result = await getRouteSearch(route.route); const variant = result.routes.flatMap((item) => item.variants).find((item) => item.variant === route.route); if (variant) navigate(`/route/${variant.route_id}`); else throw new Error(); } catch { window.dispatchEvent(new CustomEvent("naadi-toast", { detail: "Route details aren't available" })); } };
  return <div className={css.page}>
    {refreshError && <Banner tone="warning" message="Couldn't refresh. Retrying in 30 s." />}
    <h1>{first.name}</h1><p className={css.meta}>Bus stop · {ids.length} stop{ids.length === 1 ? "" : "s"} here · {new Set(merged.map((row) => row.route)).size} routes</p>
    <div className={css.actions}><Button testId="stop-plan-from" variant="primary" onClick={() => plan("from")}>Plan from here</Button><Button testId="stop-plan-to" onClick={() => plan("to")}>Plan to here</Button><Button testId="stop-share" onClick={share}>Share</Button></div>
    <p className={css.updated}>Updated {seconds} s ago · Refreshes every 30 s</p>
    <Segmented testId="stop-filter" items={[{ id: "all", label: "All" }, { id: "live", label: "Live" }]} selectedKey={filter} onChange={setFilter} />
    <div className={css.board}>{visible.length ? visible.map((row, index) => <button className={css.row} data-testid={`departure-row-${index}`} key={`${row.route}-${row.towards ?? ""}-${index}`} onClick={() => void routeFor(row)}><span><RouteBadge name={row.route} size="sm" /><span className={css.towards}>towards {row.towards ?? "—"}</span></span><span className={css.eta}>{row.live_eta_min?.length ? <><strong><i />{row.live_eta_min[0] < 1 ? "now" : `${Math.round(row.live_eta_min[0])} min`}</strong>{row.live_eta_min.length > 1 && <small>{row.live_eta_min.slice(1).map((eta) => Math.round(eta)).join(", ")} min</small>}</> : row.typical_wait_min != null ? <small>Typical wait about {Math.round(row.typical_wait_min)} min</small> : <small>No service now</small>}</span></button>) : <EmptyState title="No buses expected in the next 45 minutes" />}</div>
    <p className={css.note}>Live departures are estimates. API data is refreshed while this page is open.</p>
    {stops && <StopsOverlay data={stops} focus={[first.lon, first.lat]} onStopClick={(stopId) => navigate(`/stop/${stopId}`)} />}
  </div>;
}
