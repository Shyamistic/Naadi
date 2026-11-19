import { useEffect } from "react";
import type maplibregl from "maplibre-gl";
import { useMap } from "../MapContext";
import type { StopsAll } from "../../api/types";

const sourceId = "naadi-stops";
const layerId = "naadi-stops-points";
const labelId = "naadi-stops-labels";
const focusId = "naadi-stop-focus";
export const stopsGeoJson = (data: StopsAll) => ({ type: "FeatureCollection", features: data.stops.map(([stop_id, name, lat, lon, routes]) => ({ type: "Feature", id: stop_id, properties: { stop_id, name, routes }, geometry: { type: "Point", coordinates: [lon, lat] } })) }) as GeoJSON.FeatureCollection;

export function StopsOverlay({ data, focus, onStopClick }: { data?: StopsAll; focus?: [number, number]; onStopClick?: (stopId: number) => void }) {
  const { map, ready, styleVersion } = useMap();
  useEffect(() => {
    if (!map || !ready || !data) return;
    const source = map.getSource(sourceId);
    if (source && "setData" in source) (source as maplibregl.GeoJSONSource).setData(stopsGeoJson(data)); else map.addSource(sourceId, { type: "geojson", data: stopsGeoJson(data) });
    if (!map.getLayer(layerId)) map.addLayer({ id: layerId, type: "circle", source: sourceId, minzoom: 11, paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2, 14, 4, 18, 6], "circle-color": "#1A3A8F", "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 1 } });
    if (!map.getLayer(labelId)) map.addLayer({ id: labelId, type: "symbol", source: sourceId, minzoom: 16, layout: { "text-field": ["get", "name"], "text-size": 11, "text-offset": [0, 1.1], "text-anchor": "top", "text-allow-overlap": false }, paint: { "text-color": "#111827", "text-halo-color": "#FFFFFF", "text-halo-width": 1 } });
    const click = (event: maplibregl.MapMouseEvent) => { if (!onStopClick) return; const feature = map.queryRenderedFeatures(event.point, { layers: [layerId] })[0]; const id = Number(feature?.properties?.stop_id); if (Number.isInteger(id) && id > 0) onStopClick(id); };
    map.on("click", click);
    return () => { map.off("click", click); if (map.getLayer(labelId)) map.removeLayer(labelId); if (map.getLayer(layerId)) map.removeLayer(layerId); if (map.getSource(sourceId)) map.removeSource(sourceId); };
  }, [data, map, onStopClick, ready, styleVersion]);
  useEffect(() => {
    if (!map || !ready || !focus) return;
    const source = map.getSource("naadi-stop-focus") as maplibregl.GeoJSONSource | undefined; const geo = { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Point", coordinates: focus }, properties: {} }] } as GeoJSON.FeatureCollection;
    if (source) source.setData(geo); else map.addSource("naadi-stop-focus", { type: "geojson", data: geo });
    if (!map.getLayer(focusId)) map.addLayer({ id: focusId, type: "circle", source: "naadi-stop-focus", paint: { "circle-radius": 7, "circle-color": "#1A3A8F", "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 2 } });
    return () => { if (map.getLayer(focusId)) map.removeLayer(focusId); if (map.getSource("naadi-stop-focus")) map.removeSource("naadi-stop-focus"); };
  }, [focus, map, ready, styleVersion]);
  return null;
}
