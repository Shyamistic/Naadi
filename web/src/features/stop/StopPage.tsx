import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { useQueries, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { RouteBadge, Segmented, Button, EmptyState, ErrorState, Skeleton, Banner } from "../../ui/primitives";
import { isApiError } from "../../api/errors";
import { useStopsAll } from "../../api/queries";
import { copySharePath, getDepartures, getRouteSearch, stopIds, type StopDepartures } from "./data";
import { StopsOverlay } from "../../map/overlays/stops";
import { useMap } from "../../map/MapContext";
import { useT } from "../../i18n/I18nProvider";
import css from "./stop.module.css";

const POLL_MS = 30_000;
type Row = StopDepartures["departures"][number] & { name: string; lat: number; lon: number };

// One combined, structurally shared result for all the stops in the URL. Defined outside the component so
// react-query only recombines when a query result changes, and `rows` keeps its identity between polls.
function combineStops(results: UseQueryResult<StopDepartures>[]) {
  return {
    rows: results.flatMap((result) => result.data ? [result.data] : []),
    pending: results.some((result) => result.isPending),
    missing: results.length > 0 && results.every((result) => isApiError(result.error) && result.error.status === 404),
    refreshFailed: results.some((result) => result.isRefetchError),
    updatedAt: Math.min(...results.map((result) => result.dataUpdatedAt || Infinity)),
  };
}

export default function StopPage() {
  const { ids: rawIds } = useParams(); const navigate = useNavigate(); const { flyTo } = useMap(); const { t } = useT(); const queryClient = useQueryClient();
  // Built from the URL string, so the ids (and the query keys made from them) change only when the URL does.
  // A fresh array on every render re-ran the fetch effect after every response: over 1,000 requests a minute.
  const ids = useMemo(() => stopIds(rawIds), [rawIds]);
  const [filter, setFilter] = useState("all");
  const [now, setNow] = useState(() => Date.now());
  const board = useQueries({ queries: (ids ?? []).map((id) => ({ queryKey: ["stop-departures", id], queryFn: ({ signal }: { signal: AbortSignal }) => getDepartures(id, signal), refetchInterval: POLL_MS, staleTime: 10_000 })), combine: combineStops });
  const stops = useStopsAll();
  const first = board.rows[0];
  const focusLon = first?.lon; const focusLat = first?.lat;
  const focus = useMemo<[number, number] | undefined>(() => focusLon != null && focusLat != null ? [focusLon, focusLat] : undefined, [focusLon, focusLat]);
  // Centre on the stop when it changes, not on every refresh (that would undo the user's panning every 30 s).
  useEffect(() => { if (focus) flyTo(focus, 16); }, [flyTo, focus]);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 5000); return () => window.clearInterval(timer); }, []);
  const openStop = useCallback((stopId: number) => navigate(`/stop/${stopId}`), [navigate]);
  const merged = useMemo(() => {
    const values: Row[] = board.rows.flatMap((response) => response.departures.map((departure) => ({ ...departure, name: response.name, lat: response.lat, lon: response.lon })));
    return values.sort((a, b) => (a.live_eta_min?.[0] ?? 999) - (b.live_eta_min?.[0] ?? 999) || (a.typical_wait_min ?? 999) - (b.typical_wait_min ?? 999));
  }, [board.rows]);
  const visible = filter === "live" ? merged.filter((row) => (row.live_eta_min?.length ?? 0) > 0) : merged;
  const retry = () => void queryClient.refetchQueries({ queryKey: ["stop-departures"], type: "active" });

  if (!ids) return <ErrorState title="This stop link is invalid" body="Choose a stop from the planner." action={<Button testId="stop-home" onClick={() => navigate("/")}>Go to planner</Button>} />;
  if (!first && board.pending) return <div className={css.page} aria-busy="true"><h1><Skeleton width="65%" /></h1>{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} height="4.5rem" />)}</div>;
  if (!first && board.missing) return <EmptyState title="This stop doesn't exist" action={<Button testId="stop-home" onClick={() => navigate("/")}>Go to planner</Button>} />;
  if (!first) return <ErrorState title="Couldn't load this stop" body="Naadi keeps trying every 30 s. You can also try again now." action={<Button testId="stop-retry" onClick={retry}>Retry</Button>} />;
  const seconds = Number.isFinite(board.updatedAt) ? Math.max(0, Math.floor((now - board.updatedAt) / 1000)) : 0;
  const path = `/stop/${ids.join(",")}`;
  const plan = (kind: "from" | "to") => navigate(`/?${kind}=${first.lat},${first.lon}&${kind}Name=${encodeURIComponent(first.name)}`);
  const share = () => void copySharePath(path).then(() => window.dispatchEvent(new CustomEvent("naadi-toast", { detail: "Link copied" })));
  const routeFor = async (row: Row) => {
    if (row.route_id) { navigate(`/route/${row.route_id}`); return; }
    try {
      const variants = (await getRouteSearch(row.route)).routes.flatMap((item) => item.variants);
      const variant = variants.find((item) => item.variant === (row.route_variant ?? row.route)) ?? variants.find((item) => row.towards && item.towards === row.towards);
      if (variant) navigate(`/route/${variant.route_id}`); else throw new Error("no variant");
    } catch { window.dispatchEvent(new CustomEvent("naadi-toast", { detail: "Route details aren't available" })); }
  };
  return <div className={css.page}>
    {board.refreshFailed && <Banner tone="warning" message="Couldn't refresh. Retrying in 30 s." />}
    <h1>{first.name}</h1><p className={css.meta}>{t("stop.title")} · {ids.length} stop{ids.length === 1 ? "" : "s"} here · {new Set(merged.map((row) => row.route)).size} routes</p>
    <div className={css.actions}><Button testId="stop-plan-from" variant="primary" onClick={() => plan("from")}>{t("stop.planFrom")}</Button><Button testId="stop-plan-to" onClick={() => plan("to")}>{t("stop.planTo")}</Button><Button testId="stop-share" onClick={share}>Share</Button></div>
    <p className={css.updated}>{t("stop.updated", { seconds })} · {t("stop.refresh")}</p>
    <Segmented testId="stop-filter" items={[{ id: "all", label: t("stop.all") }, { id: "live", label: t("stop.live") }]} selectedKey={filter} onChange={setFilter} />
    <div className={css.board}>{visible.length ? visible.map((row, index) => <button className={css.row} data-testid={`departure-row-${index}`} key={`${row.route_variant ?? row.route}-${row.towards ?? ""}-${index}`} onClick={() => void routeFor(row)}><span><RouteBadge name={row.route} size="sm" /><span className={css.towards}>towards {row.towards || "—"}</span></span><span className={css.eta}>{row.live_eta_min?.length ? <><strong><i />{row.live_eta_min[0] < 1 ? "now" : `${Math.round(row.live_eta_min[0])} min`}</strong>{row.live_eta_min.length > 1 && <small>{row.live_eta_min.slice(1).map((eta) => Math.round(eta)).join(", ")} min</small>}</> : row.typical_wait_min != null ? <small>Typical wait about {Math.round(row.typical_wait_min)} min</small> : <small>No service now</small>}</span></button>) : <EmptyState title="No buses expected in the next 45 minutes" />}</div>
    <p className={css.note}>Live departures are estimates. API data is refreshed while this page is open.</p>
    {stops.data && <StopsOverlay data={stops.data} focus={focus} onStopClick={openStop} />}
  </div>;
}
