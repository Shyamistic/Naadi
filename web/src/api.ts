// Typed client for the Naadi API. Base URL: VITE_API_BASE, else "/api" (proxied by Caddy, Vercel or Vite).
export const API = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

export type Place = { name: string; lat: number; lon: number; routes?: number; stop_ids?: number[] };
export type StopRef = { stop_id: number; name: string; lat: number; lon: number; time: string };
export type WalkLeg = { type: "walk"; minutes: number; metres: number; geometry: [number, number][] };
export type BusLeg = {
  type: "bus"; route: string; route_variant: string; route_id: number; towards: string; also: string[];
  board: StopRef; alight: StopRef; wait_min: number; ride_min: number; stops: number; distance_km: number;
  fare_inr: { non_ac: number; ac: number; pink_saheli: number }; ac_share?: number | null;
  wait_source: string; next_buses_min: number[]; ride_source: string; history_samples: number;
  geometry: [number, number][];
};
export type Leg = WalkLeg | BusLeg;
export type Option = {
  labels: string[]; total_min: number; range_min: [number, number] | null; depart: string; arrive: string;
  arrive_range: [string, string] | null; transfers: number; walk_m: number; wait_min: number; ride_min: number;
  fare_inr: { non_ac: number; ac: number; pink_saheli: number }; quiet_hour: { hour: number; total_min: number } | null;
  samay_chakra: (number | null)[]; timetable_min: number | null; live: boolean; legs: Leg[];
};
export type JourneyResponse = {
  query: { from: Place; to: Place; depart: string; day_type: string; live: boolean; crow_km: number };
  options: Option[]; message?: string; model: string; attribution: string; notes: string;
};
export type Cell = { lat: number; lon: number; weekday: (number | null)[]; weekend: (number | null)[]; n: number };

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* keep status */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const searchStops = (q: string) => get<{ results: Place[] }>(`/stops/search?q=${encodeURIComponent(q)}&limit=7`);
export const planJourney = (from: string, to: string, depart: string) =>
  get<JourneyResponse>(`/journeys?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&depart=${encodeURIComponent(depart)}&options=3`);
export const vehicles = () => get<{ feed_time: string | null; vehicles: [string, string, number, number, number][] }>(`/vehicles`);
export const speedCells = () => get<{ cells: Cell[] }>(`/speeds/cells`);
export const health = () => get<{ live: { buses: number; on_route: number; residuals_30min: number; feed_ts: number } }>(`/health`);
export const accuracy = () => get<Record<string, unknown>>(`/accuracy`);
