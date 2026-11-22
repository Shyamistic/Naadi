import { useEffect } from "react";
import type maplibregl from "maplibre-gl";
import { useMap } from "../MapContext";
import type { OptionBase } from "../../api/types";
import { bearingDegrees, ensureVehicleIcons, ICON_BUS_FRESH, ICON_TRAIN } from "../vehicleIcons";

// On the journey page, a vehicle drives the chosen route from boarding to arrival and leaves a glowing trail: a bus
// on bus legs, a train on metro and Namo Bharat legs. It loops; with reduced motion it doesn't run at all.
const TRAIL = "journey-runner-trail";
const POINT = "journey-runner-point";
type SourceData = Parameters<maplibregl.GeoJSONSource["setData"]>[0];
type Step = { at: [number, number]; train: boolean };

function metres(a: [number, number], b: [number, number]) {
  const dx = (b[0] - a[0]) * 111320 * Math.cos(((a[1] + b[1]) / 2) * Math.PI / 180);
  return Math.hypot(dx, (b[1] - a[1]) * 110540);
}

export function useJourneyRunner(option: OptionBase | undefined) {
  const { map, ready, styleVersion } = useMap();
  useEffect(() => {
    if (!map || !ready || !option) return;
    if (document.documentElement.dataset.reducedMotion === "true" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const steps: Step[] = option.legs.flatMap((leg) => leg.type === "walk" ? [] : (leg.geometry ?? []).map((at) => ({ at, train: leg.type === "metro" || leg.type === "rail" })));
    if (steps.length < 2) return;
    const cum = [0];
    for (let i = 1; i < steps.length; i++) cum.push(cum[i - 1] + metres(steps[i - 1].at, steps[i].at));
    const total = cum[cum.length - 1];
    if (total < 100) return;
    ensureVehicleIcons(map);
    const empty = { type: "FeatureCollection", features: [] } as SourceData;
    if (!map.getSource(TRAIL)) map.addSource(TRAIL, { type: "geojson", data: empty });
    if (!map.getSource(POINT)) map.addSource(POINT, { type: "geojson", data: empty });
    if (!map.getLayer(TRAIL)) map.addLayer({ id: TRAIL, type: "line", source: TRAIL, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#ff9933", "line-width": 7, "line-opacity": 0.75, "line-blur": 1.5 } });
    if (!map.getLayer(POINT)) map.addLayer({ id: POINT, type: "symbol", source: POINT, layout: { "icon-image": ["get", "icon"], "icon-rotate": ["get", "bearing"], "icon-rotation-alignment": "map", "icon-pitch-alignment": "map", "icon-size": 1.25, "icon-allow-overlap": true, "icon-ignore-placement": true } });
    const runMs = Math.min(16000, Math.max(7000, total / 1000 * 650));
    const holdMs = 1400;
    let frame = 0, raf = 0, last = 0;
    const start = performance.now();
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      if (now - last < 33) return; // about 30 frames a second is plenty
      last = now;
      if (frame++ % 30 === 0) { if (map.getLayer(TRAIL)) map.moveLayer(TRAIL); if (map.getLayer(POINT)) map.moveLayer(POINT); } // stay above the route lines
      const t = Math.min(1, ((now - start) % (runMs + holdMs)) / runMs);
      const d = t * total;
      let i = 1;
      while (i < cum.length - 1 && cum[i] < d) i++;
      const a = steps[i - 1], b = steps[i];
      const f = cum[i] > cum[i - 1] ? (d - cum[i - 1]) / (cum[i] - cum[i - 1]) : 0;
      const here: [number, number] = [a.at[0] + (b.at[0] - a.at[0]) * f, a.at[1] + (b.at[1] - a.at[1]) * f];
      (map.getSource(TRAIL) as maplibregl.GeoJSONSource | undefined)?.setData({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [...steps.slice(0, i).map((s) => s.at), here] } } as SourceData);
      (map.getSource(POINT) as maplibregl.GeoJSONSource | undefined)?.setData({ type: "Feature", properties: { bearing: bearingDegrees(a.at, b.at), icon: b.train ? ICON_TRAIN : ICON_BUS_FRESH }, geometry: { type: "Point", coordinates: here } } as SourceData);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); [POINT, TRAIL].forEach((id) => { if (map.getLayer(id)) map.removeLayer(id); if (map.getSource(id)) map.removeSource(id); }); };
  }, [map, ready, styleVersion, option]);
}
