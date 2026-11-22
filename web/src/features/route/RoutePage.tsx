import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet } from "../../api/client";
import { isApiError } from "../../api/errors";
import { normalise } from "../../api/live";
import type { DayType, LiveBus, LiveBuses, RouteDetail } from "../../api/types";
import { Button, EmptyState, ErrorState, RouteBadge, Segmented, Skeleton } from "../../ui/primitives";
import { useMap } from "../../map/MapContext";
import { RouteOverlay } from "../../map/overlays/route";
import { copySharePath } from "../stop/data";
import { useT } from "../../i18n/I18nProvider";
import css from "./route.module.css";

const currentHour = () => new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000).getHours();
const chartMax = (values: (number | null)[]) => Math.max(1, ...values.filter((value): value is number => value != null));
const NO_BUSES: LiveBus[] = [];
function HourChart({ values, title, day, hour }: { values: (number | null)[]; title: string; day: DayType; hour: number }) { const max = chartMax(values); return <div className={css.chart} role="img" aria-label={`${title} for ${day}, ${values.map((value, i) => `${i}:00 ${value == null ? "no service" : value.toFixed(1)}`).join(", ")}`}><h3>{title}</h3><div className={css.bars}>{values.map((value, index) => <span key={index} title={`${String(index).padStart(2, "0")}:00`} className={index === hour ? css.current : ""} style={{ height: `${value == null ? 2 : Math.max(4, value / max * 100)}%` }} />)}</div><div className={css.chartLabels}><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div></div>; }

export default function RoutePage() {
  const { routeId } = useParams(); const navigate = useNavigate(); const { map, fitGeometry } = useMap(); const { t } = useT(); const id = Number(routeId); const valid = Number.isInteger(id) && id > 0; const hour = currentHour(); const [day, setDay] = useState<DayType>("weekday");
  // react-query owns the fetching: one request per route, day and hour, cached for the session. Before, the fetch
  // depended on the map's fitGeometry, so the route was fetched again whenever the map changed.
  const detail = useQuery({ queryKey: ["route", id, day, hour], queryFn: ({ signal }) => apiGet<RouteDetail>(`/routes/${id}?day_type=${day}&hour=${hour}`, { signal }), enabled: valid, staleTime: 600_000, placeholderData: keepPreviousData });
  const live = useQuery({ queryKey: ["route-live", id], queryFn: ({ signal }) => apiGet<LiveBuses>(`/live/buses?route_id=${id}`, { signal }), enabled: valid, refetchInterval: 15_000, staleTime: 10_000 });
  const route = detail.data && detail.data.route_id === id ? detail.data : undefined;
  const buses = useMemo(() => live.data ? normalise(live.data).buses : NO_BUSES, [live.data]);
  // Frame the route once when it first shows (and again only for a different route), not on every refresh.
  const framed = useRef<number | null>(null);
  useEffect(() => { if (!route || !map || framed.current === route.route_id) return; framed.current = route.route_id; fitGeometry(route.geometry, { padding: 64, maxZoom: 14 }); }, [route, map, fitGeometry]);
  const stopBuses = useMemo(() => route?.stops.map((stop, index) => ({ stop, buses: buses.filter((bus) => bus.progress_m != null && bus.progress_m >= stop.dist_m && (route.stops[index + 1] == null || bus.progress_m < route.stops[index + 1].dist_m)) })) ?? [], [buses, route]);
  // Switching weekday/weekend keeps showing the route while the new times load; a different route shows the skeleton.
  if (valid && !route && (detail.isPending || detail.isPlaceholderData || detail.isFetching)) return <div className={css.page} aria-busy="true"><Skeleton width="60%" height="2rem" />{Array.from({ length: 10 }, (_, i) => <Skeleton key={i} height="2.8rem" />)}</div>;
  const missing = !valid || (isApiError(detail.error) && detail.error.status === 404);
  if (missing) return <ErrorState title="Route not found" body="This route number isn't in the Delhi bus network Naadi knows." action={<Button testId="route-home" onClick={() => navigate("/")}>Go to planner</Button>} />;
  if (!route) return <ErrorState title="Couldn't load this route" body="Try again in a moment." action={<><Button testId="route-retry" onClick={() => void detail.refetch()}>Retry</Button><Button testId="route-home" onClick={() => navigate("/")}>Go to planner</Button></>} />;
  const nowStats = route.hourly[day]; const path = `/route/${route.route_id}`; const share = () => void copySharePath(path).then(() => window.dispatchEvent(new CustomEvent("naadi-toast", { detail: "Link copied" })));
  return <div className={css.page}><div className={css.heading}><RouteBadge name={route.route} size="md" /><h1>{t("route.title")} {route.route} towards {route.towards}</h1><p>From {route.from} · {route.agency === "DTC" ? "DTC" : "Cluster bus (Transport Department)"}</p></div><div className={css.actions}>{route.opposite_route_id != null && <Button testId="route-switch-direction" onClick={() => navigate(`/route/${route.opposite_route_id}`)}>{t("route.other")}</Button>}<Button testId="route-share" onClick={share}>Share</Button></div><div className={css.stats}><div><strong>{nowStats.buses_per_hour[hour] == null ? "—" : nowStats.buses_per_hour[hour].toFixed(1)}</strong><span>{t("route.busesHour")}</span></div><div><strong>{nowStats.end_to_end_min[hour] == null ? "—" : `${Math.round(nowStats.end_to_end_min[hour])} min`}</strong><span>{nowStats.end_to_end_min[hour] == null ? "No service this hour" : t("route.endToEnd")}</span></div><div><strong>{buses.length}</strong><span>{t("route.live")}</span></div></div><Segmented testId="route-daytype" items={[{ id: "weekday", label: t("route.weekday") }, { id: "weekend", label: t("route.weekend") }]} selectedKey={day} onChange={(key) => setDay(key as DayType)} /><div className={css.charts}><HourChart values={route.hourly[day].end_to_end_min} title="End-to-end minutes" day={day} hour={hour} /><HourChart values={route.hourly[day].buses_per_hour} title="Buses per hour" day={day} hour={hour} /></div>{live.isError && <p className={css.warning}>Live positions are temporarily unavailable.</p>}<ol className={css.stops}>{stopBuses.map(({ stop, buses: atStop }, index) => <li key={stop.stop_id}><span className={css.dot} /><div><Link data-testid={`route-stop-${index}`} to={`/stop/${stop.stop_id}`}>{stop.name}</Link><small>+{Math.round(stop.min_from_start)} min</small>{atStop.map((bus) => <span className={css.bus} key={bus.id}>Bus · position {Math.round(bus.age_s)} s old</span>)}</div></li>)}</ol>{live.isSuccess && buses.length === 0 && <EmptyState title="No buses on this route right now" />}<RouteOverlay route={route} buses={buses} /></div>;
}
