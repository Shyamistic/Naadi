import { apiGet } from "../../api/client";
import type { Departures, RouteSearch } from "../../api/types";

export const stopIds = (raw: string | undefined): number[] | null => {
  if (!raw) return null;
  const parts = raw.split(",");
  if (parts.length < 1 || parts.length > 6 || parts.some((part) => !/^\d+$/.test(part) || Number(part) <= 0)) return null;
  return parts.map(Number);
};

/** One stop's board, flattened: the server nests the stop's name and position under `stop`. */
export type StopDepartures = Departures;
type ServerDepartures = { stop: { stop_id: number; name: string; lat: number; lon: number }; departures: Departures["departures"] };
export const getDepartures = (id: number, signal?: AbortSignal): Promise<StopDepartures> => apiGet<StopDepartures | ServerDepartures>(`/stops/${id}/departures`, { signal }).then((response) => "stop" in response ? { ...response.stop, departures: response.departures } : response);
export const getRouteSearch = (query: string, signal?: AbortSignal) => apiGet<RouteSearch>(`/routes/search?q=${encodeURIComponent(query)}`, { signal });

export function copySharePath(path: string): Promise<void> {
  if (navigator.clipboard) return navigator.clipboard.writeText(`${window.location.origin}${path}`);
  return Promise.resolve();
}
