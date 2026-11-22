import { apiGet } from "./client";
import { isApiError } from "./errors";
import type { LiveBus, LiveBuses, Vehicles } from "./types";

const shortHash = (text: string) => { let hash = 2166136261; for (const char of text) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619); return (hash >>> 0).toString(16).padStart(8, "0"); };
/** Live positions in one shape, from the compact /live/buses rows or the older /vehicles answer. */
export const normalise = (data: LiveBuses | Vehicles): LiveBuses => "buses" in data ? { ...data, buses: (data.buses as unknown[]).flatMap((entry) => { if (Array.isArray(entry)) { const [route_id, route, variant, lat, lon, age_s, progress_m] = entry as [number | null, string, string, number, number, number, number | null]; return [{ id: shortHash(`${route_id}:${variant}:${Math.round((progress_m ?? 0) / 100)}`), route_id, route, variant, lat, lon, age_s, progress_m }]; } const bus = entry as LiveBus; return [{ ...bus, id: bus.id || shortHash(`${bus.route_id}:${bus.variant ?? bus.route}:${Math.round((bus.progress_m ?? 0) / 100)}`) }]; }) } : { feed_time: data.feed_time, count: data.vehicles.length, buses: data.vehicles.map(([id, route, lat, lon, age_s]) => ({ id: shortHash(id), route_id: null, route, lat, lon, age_s })) };

/** Every live bus. Servers without /live/buses (it answers 404) fall back to /vehicles; any other failure is
 *  reported, so a busy or unreachable server isn't asked twice. */
export async function fetchLiveBuses(signal?: AbortSignal): Promise<LiveBuses> {
  try { return normalise(await apiGet<LiveBuses>("/live/buses", { signal })); }
  catch (error) {
    if (isApiError(error) && error.kind === "http" && error.status === 404) return normalise(await apiGet<Vehicles>("/vehicles", { signal }));
    throw error;
  }
}
