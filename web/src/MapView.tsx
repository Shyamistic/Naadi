import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { PathLayer, ScatterplotLayer, ColumnLayer } from "@deck.gl/layers";
import { PathStyleExtension } from "@deck.gl/extensions";
import { duskStyle } from "./mapStyle";
import type { Cell, Option } from "./api";

type Props = {
  option: Option | null; others: Option[]; buses: [string, string, number, number, number][];
  cells: Cell[] | null; hour: number; weekend: boolean; showSpeeds: boolean; showBuses: boolean;
  from?: [number, number] | null; to?: [number, number] | null;
};

const SAFFRON: [number, number, number] = [255, 153, 51];
const GREEN: [number, number, number] = [19, 136, 8];
const speedColour = (k: number): [number, number, number, number] => {
  // slow = saffron-red, fast = green; colour-blind friendlier with brightness change
  const f = Math.max(0, Math.min(1, (k - 6) / 26));
  return [Math.round(232 - 200 * f), Math.round(70 + 110 * f), Math.round(50 + 40 * f), 210];
};

export default function MapView(p: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const overlay = useRef<MapboxOverlay | null>(null);

  useEffect(() => {
    if (!box.current) return;
    const m = new maplibregl.Map({ container: box.current, style: duskStyle, center: [77.2167, 28.6139], zoom: 10.6,
      pitch: 45, bearing: -12, maxBounds: [[76.5, 28.0], [77.9, 29.5]], attributionControl: false });
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
    m.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "Delhi Transport Stack · OTD Delhi · © OpenStreetMap · OpenFreeMap" }));
    const o = new MapboxOverlay({ interleaved: false, layers: [] });
    m.addControl(o as unknown as maplibregl.IControl);
    map.current = m; overlay.current = o;
    return () => m.remove();
  }, []);

  useEffect(() => {
    const layers: any[] = [];
    if (p.showSpeeds && p.cells) {
      const key = p.weekend ? "weekend" : "weekday";
      const data = p.cells.filter((c) => c[key][p.hour] != null);
      layers.push(new ColumnLayer({
        id: "speeds", data, diskResolution: 6, radius: 230, extruded: true, elevationScale: 1, pickable: true,
        getPosition: (c: Cell) => [c.lon, c.lat],
        getElevation: (c: Cell) => Math.max(0, 40 - (c[key][p.hour] as number)) * 45,
        getFillColor: (c: Cell) => speedColour(c[key][p.hour] as number),
        updateTriggers: { getElevation: [p.hour, key], getFillColor: [p.hour, key] },
      }));
    }
    if (p.showBuses && p.buses.length) {
      layers.push(new ScatterplotLayer({
        id: "buses", data: p.buses, getPosition: (b: any) => [b[3], b[2]], radiusUnits: "pixels", getRadius: 2.6,
        getFillColor: (b: any) => (b[4] > 120 ? [140, 150, 200, 120] : [255, 190, 110, 230]),
        transitions: { getPosition: 9000 },
      }));
    }
    const legLayers = (o: Option, idx: number, main: boolean) => {
      const bus = o.legs.filter((l) => l.type === "bus");
      const walk = o.legs.filter((l) => l.type === "walk");
      return [
        new PathLayer({ id: `bus-${idx}`, data: bus, getPath: (l: any) => l.geometry, widthUnits: "pixels",
          getWidth: main ? 6 : 3, getColor: main ? [...SAFFRON, 255] : [200, 205, 240, 110], capRounded: true, jointRounded: true }),
        new PathLayer({ id: `walk-${idx}`, data: walk, getPath: (l: any) => l.geometry, widthUnits: "pixels", getWidth: main ? 3 : 2,
          getColor: main ? [255, 255, 255, 230] : [200, 205, 240, 90], getDashArray: [3, 2], dashJustified: true,
          extensions: [new PathStyleExtension({ dash: true })] }),
      ];
    };
    p.others.forEach((o, i) => { if (o !== p.option) layers.push(...legLayers(o, i, false)); });
    if (p.option) {
      layers.push(...legLayers(p.option, 99, true));
      const stops = p.option.legs.flatMap((l) => (l.type === "bus" ? [l.board, l.alight] : []));
      layers.push(new ScatterplotLayer({ id: "stops", data: stops, getPosition: (s: any) => [s.lon, s.lat], radiusUnits: "pixels",
        getRadius: 6, getFillColor: [255, 255, 255], getLineColor: [...GREEN, 255], stroked: true, lineWidthUnits: "pixels", getLineWidth: 3 }));
    }
    const ends = [p.from && { pos: p.from, c: GREEN }, p.to && { pos: p.to, c: SAFFRON }].filter(Boolean) as any[];
    layers.push(new ScatterplotLayer({ id: "ends", data: ends, getPosition: (e: any) => [e.pos[1], e.pos[0]], radiusUnits: "pixels",
      getRadius: 9, getFillColor: (e: any) => [e.c[0], e.c[1], e.c[2], 255] as [number, number, number, number], stroked: true, getLineColor: [255, 255, 255], lineWidthUnits: "pixels", getLineWidth: 2 }));
    overlay.current?.setProps({ layers });
  }, [p.option, p.others, p.buses, p.cells, p.hour, p.weekend, p.showSpeeds, p.showBuses, p.from, p.to]);

  useEffect(() => {
    if (!p.option || !map.current) return;
    const pts = p.option.legs.flatMap((l) => l.geometry);
    if (!pts.length) return;
    const b = new maplibregl.LngLatBounds(pts[0] as [number, number], pts[0] as [number, number]);
    pts.forEach((q) => b.extend(q as [number, number]));
    const wide = window.innerWidth > 900;
    map.current.fitBounds(b, { padding: wide ? { left: 460, right: 60, top: 80, bottom: 80 } : { left: 40, right: 40, top: 60, bottom: 360 }, duration: 1200, pitch: 40 });
  }, [p.option]);

  return <div ref={box} className="map" />;
}
