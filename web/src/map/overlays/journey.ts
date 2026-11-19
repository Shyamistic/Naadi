import type maplibregl from "maplibre-gl";
import type { OptionBase, Leg } from "../../api/types";

export const JOURNEY_SOURCE = "journey-lines";
export const JOURNEY_LAYER = "journey-lines";
export function journeyGeoJSON(options: OptionBase[]) {
  return { type: "FeatureCollection", features: options.flatMap((option, optionIndex) => option.legs.flatMap((leg, legIndex) => leg.geometry?.length ? [{ type: "Feature", id: `${optionIndex}-${legIndex}`, properties: { option: optionIndex, type: leg.type, color: leg.type === "metro" ? (leg as { line_color?: string }).line_color ?? "#8E44AD" : leg.type === "bus" ? "#E8730C" : "#3A5FCC" }, geometry: { type: "LineString", coordinates: leg.geometry } }] : [])) } as GeoJSON.FeatureCollection;
}
export function ensureJourneyLayers(map: maplibregl.Map) {
  if (!map.getSource(JOURNEY_SOURCE)) map.addSource(JOURNEY_SOURCE, { type: "geojson", data: journeyGeoJSON([]) as GeoJSON.GeoJSON });
  if (!map.getLayer(JOURNEY_LAYER)) map.addLayer({ id: JOURNEY_LAYER, type: "line", source: JOURNEY_SOURCE, paint: { "line-color": ["get", "color"], "line-width": ["case", ["==", ["get", "type"], "walk"], 3, 5], "line-opacity": 0.9, "line-dasharray": [2, 2] as never } });
}
export function setJourneyOverlay(map: maplibregl.Map, options: OptionBase[], selected = 0) { ensureJourneyLayers(map); const source = map.getSource(JOURNEY_SOURCE) as maplibregl.GeoJSONSource; source.setData(journeyGeoJSON(options) as GeoJSON.GeoJSON); if (map.getLayer(JOURNEY_LAYER)) map.setPaintProperty(JOURNEY_LAYER, "line-opacity", ["case", ["==", ["get", "option"], selected], 1, 0.25]); }
export function journeyMarkers(option: OptionBase) { return option.legs.flatMap((leg: Leg) => leg.type === "bus" || leg.type === "metro" ? [{ kind: "board", name: leg.board.name, coordinates: [leg.board.lon, leg.board.lat] as [number, number] }, { kind: "alight", name: leg.alight.name, coordinates: [leg.alight.lon, leg.alight.lat] as [number, number] }] : []); }
export function clearJourneyOverlay(map: maplibregl.Map) { if (map.getLayer(JOURNEY_LAYER)) map.removeLayer(JOURNEY_LAYER); if (map.getSource(JOURNEY_SOURCE)) map.removeSource(JOURNEY_SOURCE); }
