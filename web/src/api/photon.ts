import type { Place } from "./types";

export const NCR_BBOX = { minLat: 28.15, maxLat: 29.4, minLon: 76.55, maxLon: 77.75 } as const;
export function inNcr(lat: number, lon: number) { return lat >= NCR_BBOX.minLat && lat <= NCR_BBOX.maxLat && lon >= NCR_BBOX.minLon && lon <= NCR_BBOX.maxLon; }
type Feature = { geometry?: { coordinates?: [number, number] }; properties?: Record<string, unknown> };
type PhotonResponse = { features?: Feature[] };
function photonName(p: Record<string, unknown>) { return String(p.name ?? p.street ?? p.locality ?? p.city ?? "").trim(); }
async function photonFetch(url: string, signal?: AbortSignal) {
  const controller = new AbortController(); const timeout = window.setTimeout(() => controller.abort(), 8000);
  const abort = () => controller.abort(); signal?.addEventListener("abort", abort, { once: true });
  try { const response = await fetch(url, { signal: controller.signal }); if (!response.ok) throw new Error(`Photon HTTP ${response.status}`); return await response.json() as PhotonResponse; }
  finally { window.clearTimeout(timeout); signal?.removeEventListener("abort", abort); }
}
export async function searchPhoton(query: string, signal?: AbortSignal): Promise<Place[]> {
  if (query.trim().length < 3) return [];
  const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(query.trim())}&limit=5&lang=en&bbox=${NCR_BBOX.minLon},${NCR_BBOX.minLat},${NCR_BBOX.maxLon},${NCR_BBOX.maxLat}`;
  const data = await photonFetch(url, signal);
  return (data.features ?? []).flatMap((feature): Place[] => {
    const coordinates = feature.geometry?.coordinates; const properties = feature.properties ?? {};
    if (!coordinates || coordinates.length < 2 || !inNcr(coordinates[1], coordinates[0])) return [];
    const name = photonName(properties); return name ? [{ name, lat: coordinates[1], lon: coordinates[0], kind: "place" }] : [];
  });
}
export async function reversePhoton(lat: number, lon: number, signal?: AbortSignal): Promise<Place | null> {
  if (!inNcr(lat, lon)) return null;
  const data = await photonFetch(`https://photon.komoot.io/reverse?lat=${lat}&lon=${lon}&limit=1&lang=en`, signal);
  const feature = data.features?.[0]; const coordinates = feature?.geometry?.coordinates; const name = feature ? photonName(feature.properties ?? {}) : "";
  return coordinates && name ? { name: `Near ${name}`, lat, lon, kind: "pin" } : { name: "Pinned location", lat, lon, kind: "pin" };
}
