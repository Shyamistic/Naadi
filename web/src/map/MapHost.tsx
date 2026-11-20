import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type Map as MapInstance } from "maplibre-gl";
import { buildStyle } from "./style/base";
import { MapContext, type MapApi } from "./MapContext";
import { useSettings } from "../settings/SettingsProvider";
import { MapControls } from "../components/MapControls";
import "./map.css";

type PluginApi = typeof maplibregl & {
  setRTLTextPlugin?: (url: string, lazy: boolean, callback?: (error?: Error) => void) => void;
  getRTLTextPluginStatus?: () => string;
};
const pluginApi = maplibregl as PluginApi;
let complexTextLoad: Promise<boolean> | undefined;
const encodedRangeStarts = new Set([63488, 63232, 62976, 62720, 62464, 62208, 61952, 59648, 59392, 59136, 58880, 58624, 58368, 58112, 57856, 3072, 2816, 2560, 2304, 10240, 10752]);

function loadComplexText(): Promise<boolean> {
  if (!pluginApi.setRTLTextPlugin) return Promise.resolve(false);
  if (complexTextLoad) return complexTextLoad;
  complexTextLoad = new Promise((resolve) => {
    try {
      pluginApi.setRTLTextPlugin("/maplibre-gl-complex-text.js", false);
      window.setTimeout(() => resolve(pluginApi.getRTLTextPluginStatus ? pluginApi.getRTLTextPluginStatus() !== "error" : true), 100);
    } catch { resolve(false); }
  });
  return complexTextLoad;
}

function glyphRequest(url: string) {
  const match = url.match(/(\d+)-(\d+)\.pbf$/);
  if (!match || !encodedRangeStarts.has(Number(match[1]))) return undefined;
  return { url: `https://wipfli.github.io/pgf-glyph-ranges/font/NotoSansMultiscript-Regular-v1/${match[1]}-${match[2]}.pbf` };
}

export function MapHost() {
  const { settings } = useSettings();
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapInstance | null>(null);
  const [map, setMap] = useState<MapInstance | null>(null);
  const [ready, setReady] = useState(false);
  const [styleVersion, setStyleVersion] = useState(0);
  const [mode3d, setMode3d] = useState(false);
  const [camera, setCamera] = useState({ zoom: 10.6, pitch: 0, bearing: 0, center: [77.209, 28.6139] as [number, number] });
  const pickers = useRef(new Set<(point: [number, number]) => void>());
  const api = useMemo<MapApi>(() => ({
    map, ready, styleVersion, mode3d,
    setMode3d: (value) => { setMode3d(value); map?.setPitch(value ? 50 : 0); if (map?.getLayer("building-3d")) map.setLayoutProperty("building-3d", "visibility", value ? "visible" : "none"); },
    fitGeometry: (coords, opts) => { if (coords.length) map?.fitBounds(coords.reduce((bounds, coordinate) => bounds.extend(coordinate), new maplibregl.LngLatBounds(coords[0], coords[0])), { padding: opts?.padding ?? 48, maxZoom: opts?.maxZoom, duration: 0 }); },
    flyTo: (center, zoom = 15) => map?.flyTo({ center, zoom, duration: 0 }),
    setPickMode: () => undefined,
    onPick: (callback) => { pickers.current.add(callback); return () => pickers.current.delete(callback); },
    registerClickTarget: () => () => undefined,
    addControl: (control) => map?.addControl(control), removeControl: (control) => map?.removeControl(control),
  }), [map, ready, styleVersion, mode3d]);

  useEffect(() => {
    if (!container.current) return;
    let cancelled = false;
    let instance: MapInstance | undefined;
    (async () => {
      const hindiReady = settings.lang !== "hi" || await loadComplexText();
      if (cancelled || !container.current) return;
      const language = settings.lang === "hi" && hindiReady ? "hi" : "en";
      instance = new maplibregl.Map({ container: container.current, style: buildStyle(settings.theme, language), center: [77.209, 28.6139], zoom: 10.6, minZoom: 8, maxZoom: 18.5, maxPitch: 60, maxBounds: [[75.8, 27.6], [78.6, 29.9]], renderWorldCopies: false, attributionControl: false, transformRequest: (url, resourceType) => resourceType === "Glyphs" ? glyphRequest(url) : undefined });
      mapRef.current = instance;
      setMap(instance);
      (window as Window & { __naadiMap?: MapInstance }).__naadiMap = instance;
      instance.on("load", () => { setReady(true); window.__naadiSplash?.setStatus("map"); window.__naadiSplash?.hide(); });
      instance.on("style.load", () => setStyleVersion((version) => version + 1));
      instance.on("move", () => setCamera({ zoom: instance!.getZoom(), pitch: instance!.getPitch(), bearing: instance!.getBearing(), center: [instance!.getCenter().lng, instance!.getCenter().lat] }));
      instance.on("click", (event) => pickers.current.forEach((callback) => callback([event.lngLat.lng, event.lngLat.lat])));
      if (language === "hi") {
        window.setTimeout(() => { if (pluginApi.getRTLTextPluginStatus?.() === "error" && mapRef.current === instance) instance.setStyle(buildStyle(settings.theme, "en")); }, 5000);
        instance.on("error", (event) => { if (String(event.error?.message || "").toLowerCase().includes("rtl") && mapRef.current === instance) instance.setStyle(buildStyle(settings.theme, "en")); });
      }
      const resize = new ResizeObserver(() => instance?.resize());
      resize.observe(container.current);
      (instance as MapInstance & { __naadiResize?: ResizeObserver }).__naadiResize = resize;
    })();
    return () => { cancelled = true; const resize = (instance as (MapInstance & { __naadiResize?: ResizeObserver }) | undefined)?.__naadiResize; resize?.disconnect(); instance?.remove(); delete (window as Window & { __naadiMap?: MapInstance }).__naadiMap; mapRef.current = null; setMap(null); setReady(false); };
  }, []);

  useEffect(() => {
    const instance = mapRef.current;
    if (!instance || !ready) return;
    let cancelled = false;
    (async () => {
      const hindiReady = settings.lang !== "hi" || await loadComplexText();
      if (!cancelled && mapRef.current === instance) instance.setStyle(buildStyle(settings.theme, settings.lang === "hi" && hindiReady ? "hi" : "en"));
    })();
    return () => { cancelled = true; };
  }, [settings.theme, settings.lang, ready]);

  return <MapContext.Provider value={api}><div className="map-wrap"><div ref={container} className="map-canvas" data-testid="map" data-control aria-label="Map. Use arrow keys to pan, equals and minus to zoom." data-ready={ready} data-style={settings.theme} data-zoom={camera.zoom.toFixed(2)} data-pitch={Math.round(camera.pitch)} data-bearing={Math.round(camera.bearing)} data-center={`${camera.center[0].toFixed(5)},${camera.center[1].toFixed(5)}`} /><div className="map-attribution"><a data-testid="attr-osm" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a> · <a data-testid="attr-ofm" href="https://openfreemap.org/" target="_blank" rel="noopener noreferrer">OpenFreeMap</a> · <a data-testid="attr-omt" href="https://www.openmaptiles.org/" target="_blank" rel="noopener noreferrer">OpenMapTiles</a></div></div><MapControls /></MapContext.Provider>;
}
