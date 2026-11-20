export type Place = { name: string; lat: number; lon: number; kind: "stop" | "place" | "pin" | "location" };
export type RecentJourney = { from: Place; to: Place; at: number };
export type PlacesState = { home?: Place; work?: Place; recent: RecentJourney[] };
const KEY = "naadi.places.v1";
export const emptyPlaces = (): PlacesState => ({ recent: [] });
export function readPlaces(): PlacesState { try { const value = JSON.parse(localStorage.getItem(KEY) || "null") as Partial<PlacesState> | null; if (!value || !Array.isArray(value.recent)) return emptyPlaces(); return { home: value.home, work: value.work, recent: value.recent.slice(0, 8) }; } catch { return emptyPlaces(); } }
export function writePlaces(value: PlacesState) { try { localStorage.setItem(KEY, JSON.stringify(value)); } catch { /* storage is optional */ } }
export function savePlace(slot: "home" | "work", place: Place) { const next = readPlaces(); next[slot] = place; writePlaces(next); return next; }
export function addRecent(from: Place, to: Place) { if (from.kind === "location" || to.kind === "location") return readPlaces(); const next = readPlaces(); next.recent = [{ from, to, at: Date.now() }, ...next.recent.filter((j) => j.from.name !== from.name || j.to.name !== to.name)].slice(0, 8); writePlaces(next); return next; }
