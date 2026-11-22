import { useEffect } from "react";
import type maplibregl from "maplibre-gl";
import { useMap } from "../MapContext";
import { usePulse } from "../../api/queries";
import type { Pulse } from "../../api/types";

// The city's pulse on the home map: a softly breathing heat glow where buses are on the road right now, and the
// stretches where buses are taking much longer than usual drawn in red. Both come from GET /pulse.
const DENSITY = "naadi-pulse-density";
const SLOW = "naadi-pulse-slow";
const HEAT = "naadi-pulse-heat";
const GLOW = "naadi-pulse-slow-glow";
const LINE = "naadi-pulse-slow-line";
type SourceData = Parameters<maplibregl.GeoJSONSource["setData"]>[0];
const EMPTY = { type: "FeatureCollection", features: [] } as SourceData;

const densityData = (pulse: Pulse) => ({ type: "FeatureCollection", features: pulse.density.map(([lon, lat, n]) => ({ type: "Feature", properties: { n }, geometry: { type: "Point", coordinates: [lon, lat] } })) }) as SourceData;
const slowData = (pulse: Pulse) => ({ type: "FeatureCollection", features: pulse.slow.map((s) => ({ type: "Feature", properties: { ratio: s.ratio, name: `${s.from} → ${s.to}` }, geometry: { type: "LineString", coordinates: s.coords } })) }) as SourceData;
const intensity = (k: number) => ["interpolate", ["linear"], ["zoom"], 9, 0.9 * k, 13, 1.7 * k] as unknown as maplibregl.ExpressionSpecification;
const reducedMotion = () => document.documentElement.dataset.reducedMotion === "true" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function PulseOverlay() {
  const { map, ready, styleVersion } = useMap();
  const { data } = usePulse();
  useEffect(() => {
    if (!map || !ready) return;
    if (!map.getSource(DENSITY)) map.addSource(DENSITY, { type: "geojson", data: EMPTY });
    if (!map.getSource(SLOW)) map.addSource(SLOW, { type: "geojson", data: EMPTY });
    if (!map.getLayer(HEAT)) map.addLayer({ id: HEAT, type: "heatmap", source: DENSITY, maxzoom: 15, paint: {
      "heatmap-weight": ["interpolate", ["linear"], ["get", "n"], 1, 0.35, 8, 1],
      "heatmap-intensity": intensity(1),
      "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 9, 9, 11, 16, 13, 30, 14.5, 44],
      "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(255,153,51,0)", 0.08, "rgba(255,170,90,0.16)", 0.3, "rgba(255,150,60,0.36)", 0.55, "rgba(240,120,30,0.52)", 0.8, "rgba(220,80,20,0.64)", 1, "rgba(185,28,28,0.72)"],
      "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 12.5, 0.9, 15, 0],
    } });
    if (!map.getLayer(GLOW)) map.addLayer({ id: GLOW, type: "line", source: SLOW, layout: { "line-cap": "round" }, paint: { "line-color": "#dc2626", "line-width": ["interpolate", ["linear"], ["zoom"], 10, 8, 15, 18], "line-blur": 6, "line-opacity": 0.35 } });
    if (!map.getLayer(LINE)) map.addLayer({ id: LINE, type: "line", source: SLOW, layout: { "line-cap": "round" }, paint: { "line-color": "#b91c1c", "line-width": ["interpolate", ["linear"], ["zoom"], 10, 2.5, 15, 6] } });
    return () => { [LINE, GLOW, HEAT].forEach((id) => { if (map.getLayer(id)) map.removeLayer(id); }); [SLOW, DENSITY].forEach((id) => { if (map.getSource(id)) map.removeSource(id); }); };
  }, [map, ready, styleVersion]);
  useEffect(() => {
    if (!map || !ready || !data) return;
    (map.getSource(DENSITY) as maplibregl.GeoJSONSource | undefined)?.setData(data.stale ? EMPTY : densityData(data));
    (map.getSource(SLOW) as maplibregl.GeoJSONSource | undefined)?.setData(data.stale ? EMPTY : slowData(data));
  }, [map, ready, styleVersion, data]);
  useEffect(() => {
    if (!map || !ready || reducedMotion()) return;
    const start = performance.now();
    const timer = window.setInterval(() => { if (map.getLayer(HEAT)) map.setPaintProperty(HEAT, "heatmap-intensity", intensity(1 + 0.18 * Math.sin((performance.now() - start) / 2400 * Math.PI * 2))); }, 140);
    return () => window.clearInterval(timer);
  }, [map, ready, styleVersion]);
  return null;
}
