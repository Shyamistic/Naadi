import { useEffect } from "react";
import type maplibregl from "maplibre-gl";
import { useMap } from "../MapContext";
import type { LiveBus, RouteDetail } from "../../api/types";

const lineSource = "naadi-route-line";
const stopSource = "naadi-route-stops";
const busSource = "naadi-route-buses";
const clean = (map: maplibregl.Map, layerIds: string[], sourceIds: string[]) => { layerIds.forEach((id) => { if (map.getLayer(id)) map.removeLayer(id); }); sourceIds.forEach((id) => { if (map.getSource(id)) map.removeSource(id); }); };

export function RouteOverlay({ route, buses }: { route: RouteDetail; buses: LiveBus[] }) {
  const { map, ready, styleVersion } = useMap();
  useEffect(() => {
    if (!map || !ready) return;
    const line = { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "LineString", coordinates: route.geometry }, properties: {} }] } as GeoJSON.FeatureCollection;
    const stops = { type: "FeatureCollection", features: route.stops.map((stop) => ({ type: "Feature", id: stop.stop_id, geometry: { type: "Point", coordinates: [stop.lon, stop.lat] }, properties: { stop_id: stop.stop_id, name: stop.name } })) } as GeoJSON.FeatureCollection;
    const live = { type: "FeatureCollection", features: buses.map((bus) => ({ type: "Feature", id: bus.id, geometry: { type: "Point", coordinates: [bus.lon, bus.lat] }, properties: { age_s: bus.age_s } })) } as GeoJSON.FeatureCollection;
    const setOrAdd = (id: string, data: GeoJSON.FeatureCollection) => { const source = map.getSource(id) as maplibregl.GeoJSONSource | undefined; if (source) source.setData(data); else map.addSource(id, { type: "geojson", data }); };
    setOrAdd(lineSource, line); setOrAdd(stopSource, stops); setOrAdd(busSource, live);
    if (!map.getLayer("naadi-route-casing")) map.addLayer({ id: "naadi-route-casing", type: "line", source: lineSource, paint: { "line-color": "#FFFFFF", "line-width": 9, "line-opacity": 0.85 } });
    if (!map.getLayer("naadi-route-line")) map.addLayer({ id: "naadi-route-line", type: "line", source: lineSource, paint: { "line-color": "#E8730C", "line-width": 5 } });
    if (!map.getLayer("naadi-route-stops")) map.addLayer({ id: "naadi-route-stops", type: "circle", source: stopSource, paint: { "circle-radius": 5, "circle-color": "#FFFFFF", "circle-stroke-color": "#E8730C", "circle-stroke-width": 2 } });
    if (!map.getLayer("naadi-route-buses")) map.addLayer({ id: "naadi-route-buses", type: "circle", source: busSource, paint: { "circle-radius": 7, "circle-color": "#138808", "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 2 } });
    return () => clean(map, ["naadi-route-casing", "naadi-route-line", "naadi-route-stops", "naadi-route-buses"], [lineSource, stopSource, busSource]);
  }, [buses, map, ready, route, styleVersion]);
  return null;
}
