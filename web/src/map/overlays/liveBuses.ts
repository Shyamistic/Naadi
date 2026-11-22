import { useEffect } from "react";
import type maplibregl from "maplibre-gl";
import { useMap } from "../MapContext";
import type { LiveBus } from "../../api/types";
import { ensureVehicleIcons, headingFor, ICON_BUS_FRESH, ICON_BUS_STALE } from "../vehicleIcons";

// Zoomed out: clusters with counts, then dots. Zoom 14 to 16: a bus icon pointing the way the bus is going.
// From zoom 16: a 3D bus body (fill-extrusion), also facing its direction of travel. Tilt the map to see the depth.
const ICON_MIN_ZOOM = 14;
const BODY_MIN_ZOOM = 16;
const SOURCE = "naadi-buses";
const SOURCE_3D = "naadi-bus-3d";
const LAYERS = ["naadi-bus-labels", "naadi-bus-3d", "naadi-bus-icons", "naadi-bus-points", "naadi-bus-cluster-count", "naadi-bus-clusters"];
const FRESH_S = 120;

export const busFeatureCollection = (buses: LiveBus[]) => ({
  type: "FeatureCollection",
  features: buses.map((bus) => ({
    type: "Feature", id: bus.id,
    properties: { route: bus.route ?? "Unknown", route_id: bus.route_id, age_s: bus.age_s, bearing: headingFor(bus.id, [bus.lon, bus.lat]) },
    geometry: { type: "Point", coordinates: [bus.lon, bus.lat] },
  })),
}) as GeoJSON.FeatureCollection;

// A Delhi low-floor bus is about 12 m long, 2.6 m wide and 3.2 m tall. The body is drawn at s times that size so it
// stays about 20 px long on screen as you zoom (s = 1 from zoom 17.6). Parts are stacked, never overlapping, so the
// renderer doesn't flicker between them: dark underbody, coloured lower body, window band, roof (shorter at the
// front so the windscreen shows which way the bus faces).
const PALETTE = { fresh: { body: "#22a447", roof: "#f4fbf5" }, stale: { body: "#a3acb9", roof: "#f3f4f6" } };
function busBody(bus: LiveBus, bearing: number, s: number): GeoJSON.Feature[] {
  const mLat = 1 / 111320;
  const mLon = 1 / (111320 * Math.cos((bus.lat * Math.PI) / 180));
  const th = (bearing * Math.PI) / 180;
  const fx = Math.sin(th), fy = Math.cos(th);   // forward, as (east, north)
  const rx = Math.cos(th), ry = -Math.sin(th);  // to the bus's right
  // Width is drawn 1.4 times real so the bodies read as buses, not slivers, when the map is tilted.
  const rect = (back: number, front: number, halfWidth: number) => [[[back, -halfWidth * 1.4], [front, -halfWidth * 1.4], [front, halfWidth * 1.4], [back, halfWidth * 1.4], [back, -halfWidth * 1.4]].map(([a, b]) => [bus.lon + (a * fx + b * rx) * s * mLon, bus.lat + (a * fy + b * ry) * s * mLat])];
  const colours = bus.age_s < FRESH_S ? PALETTE.fresh : PALETTE.stale;
  const part = (name: string, base: number, top: number, coordinates: number[][][], colour: string): GeoJSON.Feature => ({ type: "Feature", properties: { bus: bus.id, part: name, base: base * s, top: top * s, colour }, geometry: { type: "Polygon", coordinates } });
  return [
    part("under", 0, 0.4, rect(-4.6, 4.6, 1.1), "#374151"),
    part("lower", 0.4, 1.45, rect(-6, 6, 1.3), colours.body),
    part("windows", 1.45, 2.5, rect(-5.85, 6, 1.28), "#475569"),
    part("roof", 2.5, 3.0, rect(-6, 5.1, 1.3), colours.roof),
  ];
}

export function LiveBusesOverlay({ buses, onBusClick }: { buses: LiveBus[]; onBusClick?: (bus: LiveBus) => void }) {
  const { map, ready, styleVersion } = useMap();
  useEffect(() => {
    if (!map || !ready) return;
    ensureVehicleIcons(map);
    const source = map.getSource(SOURCE) as maplibregl.GeoJSONSource | undefined;
    const data = busFeatureCollection(buses);
    if (source) source.setData(data); else map.addSource(SOURCE, { type: "geojson", data, cluster: true, clusterMaxZoom: 12, clusterRadius: 48, clusterProperties: { total: ["+", 1] } });
    if (!map.getSource(SOURCE_3D)) map.addSource(SOURCE_3D, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    if (!map.getLayer("naadi-bus-clusters")) map.addLayer({ id: "naadi-bus-clusters", type: "circle", source: SOURCE, filter: ["has", "point_count"], paint: { "circle-color": "#1A3A8F", "circle-radius": ["step", ["get", "point_count"], 16, 50, 20, 200, 26], "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 2 } });
    if (!map.getLayer("naadi-bus-cluster-count")) map.addLayer({ id: "naadi-bus-cluster-count", type: "symbol", source: SOURCE, filter: ["has", "point_count"], layout: { "text-field": ["get", "point_count_abbreviated"], "text-font": ["Noto Sans Bold"], "text-size": 12 }, paint: { "text-color": "#FFFFFF" } });
    if (!map.getLayer("naadi-bus-points")) map.addLayer({ id: "naadi-bus-points", type: "circle", source: SOURCE, maxzoom: ICON_MIN_ZOOM, filter: ["!", ["has", "point_count"]], paint: { "circle-color": ["case", ["<", ["get", "age_s"], FRESH_S], "#138808", "#9CA3AF"], "circle-radius": 6, "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 1.5 } });
    if (!map.getLayer("naadi-bus-icons") && map.hasImage(ICON_BUS_FRESH)) map.addLayer({
      id: "naadi-bus-icons", type: "symbol", source: SOURCE, minzoom: ICON_MIN_ZOOM, maxzoom: BODY_MIN_ZOOM, filter: ["!", ["has", "point_count"]],
      layout: { "icon-image": ["case", ["<", ["get", "age_s"], FRESH_S], ICON_BUS_FRESH, ICON_BUS_STALE], "icon-rotate": ["get", "bearing"], "icon-rotation-alignment": "map", "icon-pitch-alignment": "map", "icon-size": ["interpolate", ["linear"], ["zoom"], 14, 0.7, 16, 1.05], "icon-allow-overlap": true, "icon-ignore-placement": true },
    });
    if (!map.getLayer("naadi-bus-3d")) map.addLayer({ id: "naadi-bus-3d", type: "fill-extrusion", source: SOURCE_3D, minzoom: BODY_MIN_ZOOM, paint: { "fill-extrusion-color": ["get", "colour"], "fill-extrusion-base": ["get", "base"], "fill-extrusion-height": ["get", "top"], "fill-extrusion-opacity": 1, "fill-extrusion-vertical-gradient": true } });
    if (!map.getLayer("naadi-bus-labels")) map.addLayer({ id: "naadi-bus-labels", type: "symbol", source: SOURCE, minzoom: 15, filter: ["!", ["has", "point_count"]], layout: { "text-field": ["get", "route"], "text-font": ["Noto Sans Regular"], "text-size": 11, "text-offset": [0, 1.9] }, paint: { "text-color": "#111827", "text-halo-color": "#FFFFFF", "text-halo-width": 1 } });
    // Only buses near the view get a body; rebuilt after every move and every poll.
    const update3d = () => {
      const body = map.getSource(SOURCE_3D) as maplibregl.GeoJSONSource | undefined;
      if (!body) return;
      const zoom = map.getZoom();
      if (zoom < BODY_MIN_ZOOM - 0.5) { body.setData({ type: "FeatureCollection", features: [] }); return; }
      const bounds = map.getBounds();
      const padLon = (bounds.getEast() - bounds.getWest()) * 0.3, padLat = (bounds.getNorth() - bounds.getSouth()) * 0.3;
      const s = Math.min(6, Math.max(1, 2 ** (18 - zoom)));
      const near = buses.filter((bus) => bus.lon > bounds.getWest() - padLon && bus.lon < bounds.getEast() + padLon && bus.lat > bounds.getSouth() - padLat && bus.lat < bounds.getNorth() + padLat);
      body.setData({ type: "FeatureCollection", features: near.slice(0, 600).flatMap((bus) => busBody(bus, headingFor(bus.id, [bus.lon, bus.lat]), s)) });
    };
    update3d();
    map.on("moveend", update3d);
    const click = (event: maplibregl.MapMouseEvent) => {
      const layers = ["naadi-bus-3d", "naadi-bus-icons", "naadi-bus-points", "naadi-bus-clusters"].filter((id) => map.getLayer(id));
      const feature = map.queryRenderedFeatures(event.point, { layers })[0];
      if (!feature) return;
      if (feature.properties?.cluster_id != null) {
        const clusterSource = map.getSource(SOURCE) as maplibregl.GeoJSONSource | undefined;
        if (clusterSource) void clusterSource.getClusterExpansionZoom(Number(feature.properties.cluster_id)).then((zoom) => map.easeTo({ center: (feature.geometry as GeoJSON.Point).coordinates as [number, number], zoom, duration: 280 }));
        return;
      }
      const id = String(feature.properties?.bus ?? feature.id ?? "");
      const bus = buses.find((item) => item.id === id);
      if (bus) onBusClick?.(bus);
    };
    map.on("click", click);
    return () => {
      map.off("click", click);
      map.off("moveend", update3d);
      LAYERS.forEach((id) => { if (map.getLayer(id)) map.removeLayer(id); });
      [SOURCE_3D, SOURCE].forEach((id) => { if (map.getSource(id)) map.removeSource(id); });
    };
  }, [buses, map, onBusClick, ready, styleVersion]);
  return null;
}
