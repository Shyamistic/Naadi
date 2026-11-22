import { useEffect } from "react";
import type maplibregl from "maplibre-gl";
import { useMap } from "../MapContext";
import type { LiveBus } from "../../api/types";
import { ensureVehicleIcons, headingFor, ICON_BUS_FRESH, ICON_BUS_STALE } from "../vehicleIcons";

export const busFeatureCollection = (buses: LiveBus[]) => ({
  type: "FeatureCollection",
  features: buses.map((bus) => ({
    type: "Feature", id: bus.id,
    properties: { route: bus.route ?? "Unknown", route_id: bus.route_id, age_s: bus.age_s, bearing: headingFor(bus.id, [bus.lon, bus.lat]) },
    geometry: { type: "Point", coordinates: [bus.lon, bus.lat] },
  })),
}) as GeoJSON.FeatureCollection;

// Zoomed out: clusters with counts, then dots. From zoom 14: a bus icon pointing the way the bus is going.
const ICON_MIN_ZOOM = 14;
const LAYERS = ["naadi-bus-labels", "naadi-bus-icons", "naadi-bus-points", "naadi-bus-cluster-count", "naadi-bus-clusters"];

export function LiveBusesOverlay({ buses, onBusClick }: { buses: LiveBus[]; onBusClick?: (bus: LiveBus) => void }) {
  const { map, ready, styleVersion } = useMap();
  useEffect(() => {
    if (!map || !ready) return;
    const sourceId = "naadi-buses";
    ensureVehicleIcons(map);
    const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
    const data = busFeatureCollection(buses);
    if (source) source.setData(data); else map.addSource(sourceId, { type: "geojson", data, cluster: true, clusterMaxZoom: 12, clusterRadius: 48, clusterProperties: { total: ["+", 1] } });
    if (!map.getLayer("naadi-bus-clusters")) map.addLayer({ id: "naadi-bus-clusters", type: "circle", source: sourceId, filter: ["has", "point_count"], paint: { "circle-color": "#1A3A8F", "circle-radius": ["step", ["get", "point_count"], 16, 50, 20, 200, 26], "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 2 } });
    if (!map.getLayer("naadi-bus-cluster-count")) map.addLayer({ id: "naadi-bus-cluster-count", type: "symbol", source: sourceId, filter: ["has", "point_count"], layout: { "text-field": ["get", "point_count_abbreviated"], "text-font": ["Noto Sans Bold"], "text-size": 12 }, paint: { "text-color": "#FFFFFF" } });
    if (!map.getLayer("naadi-bus-points")) map.addLayer({ id: "naadi-bus-points", type: "circle", source: sourceId, maxzoom: ICON_MIN_ZOOM, filter: ["!", ["has", "point_count"]], paint: { "circle-color": ["case", ["<", ["get", "age_s"], 120], "#138808", "#9CA3AF"], "circle-radius": 6, "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 1.5 } });
    if (!map.getLayer("naadi-bus-icons") && map.hasImage(ICON_BUS_FRESH)) map.addLayer({
      id: "naadi-bus-icons", type: "symbol", source: sourceId, minzoom: ICON_MIN_ZOOM, filter: ["!", ["has", "point_count"]],
      layout: {
        "icon-image": ["case", ["<", ["get", "age_s"], 120], ICON_BUS_FRESH, ICON_BUS_STALE],
        "icon-rotate": ["get", "bearing"], "icon-rotation-alignment": "map", "icon-pitch-alignment": "map",
        "icon-size": ["interpolate", ["linear"], ["zoom"], 14, 0.7, 17, 1.1, 19, 1.5],
        "icon-allow-overlap": true, "icon-ignore-placement": true,
      },
    });
    if (!map.getLayer("naadi-bus-labels")) map.addLayer({ id: "naadi-bus-labels", type: "symbol", source: sourceId, minzoom: 15, filter: ["!", ["has", "point_count"]], layout: { "text-field": ["get", "route"], "text-font": ["Noto Sans Regular"], "text-size": 11, "text-offset": [0, 1.9] }, paint: { "text-color": "#111827", "text-halo-color": "#FFFFFF", "text-halo-width": 1 } });
    const click = (event: maplibregl.MapMouseEvent) => {
      const layers = ["naadi-bus-icons", "naadi-bus-points", "naadi-bus-clusters"].filter((id) => map.getLayer(id));
      const feature = map.queryRenderedFeatures(event.point, { layers })[0];
      if (!feature) return;
      if (feature.properties?.cluster_id != null) {
        const clusterSource = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
        if (clusterSource) void clusterSource.getClusterExpansionZoom(Number(feature.properties.cluster_id)).then((zoom) => map.easeTo({ center: (feature.geometry as GeoJSON.Point).coordinates as [number, number], zoom, duration: 280 }));
        return;
      }
      const id = String(feature.id ?? "");
      const bus = buses.find((item) => item.id === id);
      if (bus) onBusClick?.(bus);
    };
    map.on("click", click);
    return () => {
      map.off("click", click);
      LAYERS.forEach((id) => { if (map.getLayer(id)) map.removeLayer(id); });
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    };
  }, [buses, map, onBusClick, ready, styleVersion]);
  return null;
}
