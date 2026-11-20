import type maplibregl from "maplibre-gl";
import type { OptionBase, Leg } from "../../api/types";
type SourceData = Parameters<maplibregl.GeoJSONSource["setData"]>[0];

export const JOURNEY_SOURCE = "journey-lines";
export const JOURNEY_LAYER = "journey-lines";
const MARKER_SOURCE = "journey-markers";
const MARKER_LAYER = "journey-markers";
export function journeyGeoJSON(options: OptionBase[]) {
  return { type: "FeatureCollection", features: options.flatMap((option, optionIndex) => option.legs.flatMap((leg, legIndex) => leg.geometry?.length ? [{ type: "Feature", id: `${optionIndex}-${legIndex}`, properties: { option: optionIndex, type: leg.type, color: leg.type === "metro" ? (leg as { line_color?: string }).line_color ?? "#8E44AD" : leg.type === "bus" ? "#E8730C" : "#3A5FCC" }, geometry: { type: "LineString", coordinates: leg.geometry } }] : [])) } as SourceData;
}
function markerGeoJSON(option?: OptionBase): SourceData {
  return { type: "FeatureCollection", features: option ? journeyMarkers(option).map((marker, index) => ({ type: "Feature", id: `marker-${index}`, properties: { kind: marker.kind, name: marker.name }, geometry: { type: "Point", coordinates: marker.coordinates } })) : [] } as SourceData;
}
export function ensureJourneyLayers(map: maplibregl.Map) {
  if (!map.getSource(JOURNEY_SOURCE)) map.addSource(JOURNEY_SOURCE, { type: "geojson", data: journeyGeoJSON([]) as SourceData });
  if (!map.getLayer(JOURNEY_LAYER)) map.addLayer({ id: JOURNEY_LAYER, type: "line", source: JOURNEY_SOURCE, paint: { "line-color": ["get", "color"], "line-width": ["case", ["==", ["get", "type"], "walk"], 3, 5], "line-opacity": 0.9, "line-dasharray": [2, 2] as never } });
  if (!map.getSource(MARKER_SOURCE)) map.addSource(MARKER_SOURCE, { type: "geojson", data: markerGeoJSON() });
  if (!map.getLayer(MARKER_LAYER)) map.addLayer({ id: MARKER_LAYER, type: "circle", source: MARKER_SOURCE, paint: { "circle-radius": 7, "circle-color": ["match", ["get", "kind"], "board", "#1A3A8F", "#E8730C"], "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 2 } });
}
export function setJourneyOverlay(map: maplibregl.Map, options: OptionBase[], selected = 0) { ensureJourneyLayers(map); const source = map.getSource(JOURNEY_SOURCE) as maplibregl.GeoJSONSource; source.setData(journeyGeoJSON(options) as SourceData); const markers = map.getSource(MARKER_SOURCE) as maplibregl.GeoJSONSource; markers.setData(markerGeoJSON(options[selected] ?? options[0]) as SourceData); if (map.getLayer(JOURNEY_LAYER)) map.setPaintProperty(JOURNEY_LAYER, "line-opacity", ["case", ["==", ["get", "option"], selected], 1, 0.25]); }
export function journeyMarkers(option: OptionBase) { return option.legs.flatMap((leg: Leg) => leg.type === "bus" || leg.type === "metro" ? [{ kind: "board", name: leg.board.name, coordinates: [leg.board.lon, leg.board.lat] as [number, number] }, { kind: "alight", name: leg.alight.name, coordinates: [leg.alight.lon, leg.alight.lat] as [number, number] }] : []); }
export function clearJourneyOverlay(map: maplibregl.Map) { if (map.getLayer(JOURNEY_LAYER)) map.removeLayer(JOURNEY_LAYER); if (map.getSource(JOURNEY_SOURCE)) map.removeSource(JOURNEY_SOURCE); if (map.getLayer(MARKER_LAYER)) map.removeLayer(MARKER_LAYER); if (map.getSource(MARKER_SOURCE)) map.removeSource(MARKER_SOURCE); }
