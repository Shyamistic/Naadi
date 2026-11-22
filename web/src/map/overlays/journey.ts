import type maplibregl from "maplibre-gl";
import type { OptionBase, Leg } from "../../api/types";
type SourceData = Parameters<maplibregl.GeoJSONSource["setData"]>[0];
export const JOURNEY_SOURCE = "journey-lines";
export const JOURNEY_LAYER = "journey-lines";
const CASING_LAYER = "journey-lines-casing";
const MARKER_SOURCE = "journey-markers";
const MARKER_LAYER = "journey-markers";
const BUS_COLORS = ["#E8730C", "#1A3A8F", "#008A6B", "#A63D40"];
function busColor(route: string) { return BUS_COLORS[[...route].reduce((sum, character) => sum + character.charCodeAt(0), 0) % BUS_COLORS.length]; }
function transitLeg(leg: Leg): leg is Exclude<Leg, { type: "walk" }> { return leg.type !== "walk"; }
export function journeyGeoJSON(options: OptionBase[]) { return { type: "FeatureCollection", features: options.flatMap((option, optionIndex) => option.legs.flatMap((leg, legIndex) => leg.geometry?.length ? [{ type: "Feature", id: `${optionIndex}-${legIndex}`, properties: { option: optionIndex, type: leg.type, color: leg.type === "metro" ? leg.line_color : leg.type === "bus" ? busColor(leg.route) : leg.type === "rail" ? "#00838F" : leg.type === "shared_auto" ? "#B35C00" : "#3A5FCC" }, geometry: { type: "LineString", coordinates: leg.geometry } }] : [])) } as SourceData; }
function markerGeoJSON(option?: OptionBase): SourceData { return { type: "FeatureCollection", features: option ? journeyMarkers(option).map((marker, index) => ({ type: "Feature", id: `marker-${index}`, properties: { kind: marker.kind, name: marker.name }, geometry: { type: "Point", coordinates: marker.coordinates } })) : [] } as SourceData; }
export function ensureJourneyLayers(map: maplibregl.Map) {
  if (!map.getSource(JOURNEY_SOURCE)) map.addSource(JOURNEY_SOURCE, { type: "geojson", data: journeyGeoJSON([]) as SourceData });
  // A white casing under the selected option makes it stand out from the other options and from the base map.
  if (!map.getLayer(CASING_LAYER)) map.addLayer({ id: CASING_LAYER, type: "line", source: JOURNEY_SOURCE, filter: ["==", ["get", "option"], 0], layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#FFFFFF", "line-width": ["case", ["==", ["get", "type"], "walk"], 6, 10], "line-opacity": 0.95 } });
  if (!map.getLayer(JOURNEY_LAYER)) map.addLayer({ id: JOURNEY_LAYER, type: "line", source: JOURNEY_SOURCE, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["get", "color"], "line-width": ["case", ["==", ["get", "type"], "walk"], 3, 5], "line-opacity": 0.9, "line-dasharray": ["case", ["==", ["get", "type"], "walk"], ["literal", [2, 2]], ["literal", [1, 0]]] as never } });
  if (!map.getSource(MARKER_SOURCE)) map.addSource(MARKER_SOURCE, { type: "geojson", data: markerGeoJSON() });
  if (!map.getLayer(MARKER_LAYER)) map.addLayer({ id: MARKER_LAYER, type: "circle", source: MARKER_SOURCE, paint: { "circle-radius": 7, "circle-color": ["match", ["get", "kind"], "board", "#1A3A8F", "#E8730C"], "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 2 } });
}
export function setJourneyOverlay(map: maplibregl.Map, options: OptionBase[], selected = 0) {
  ensureJourneyLayers(map);
  (map.getSource(JOURNEY_SOURCE) as maplibregl.GeoJSONSource).setData(journeyGeoJSON(options) as SourceData);
  (map.getSource(MARKER_SOURCE) as maplibregl.GeoJSONSource).setData(markerGeoJSON(options[selected] ?? options[0]) as SourceData);
  const isSelected = ["==", ["get", "option"], selected] as maplibregl.ExpressionSpecification;
  if (map.getLayer(CASING_LAYER)) map.setFilter(CASING_LAYER, isSelected);
  if (map.getLayer(JOURNEY_LAYER)) {
    map.setPaintProperty(JOURNEY_LAYER, "line-opacity", ["case", isSelected, 1, 0.28]);
    map.setPaintProperty(JOURNEY_LAYER, "line-width", ["case", ["==", ["get", "type"], "walk"], ["case", isSelected, 3.5, 2.5], ["case", isSelected, 6, 3.5]]);
  }
}
export function journeyMarkers(option: OptionBase) { return option.legs.flatMap((leg: Leg) => { if (!transitLeg(leg)) return []; const board = "board" in leg ? leg.board : undefined; const alight = "alight" in leg ? leg.alight : undefined; return board && alight ? [{ kind: "board", name: board.name, coordinates: [board.lon, board.lat] as [number, number] }, { kind: "alight", name: alight.name, coordinates: [alight.lon, alight.lat] as [number, number] }] : []; }); }
export function clearJourneyOverlay(map: maplibregl.Map) { [MARKER_LAYER, JOURNEY_LAYER, CASING_LAYER].forEach((id) => { if (map.getLayer(id)) map.removeLayer(id); }); [MARKER_SOURCE, JOURNEY_SOURCE].forEach((id) => { if (map.getSource(id)) map.removeSource(id); }); }
