import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import maplibregl, { type Map as MapInstance } from "maplibre-gl";
import { buildStyle } from "./style/base";
import { MapContext, type MapApi } from "./MapContext";
import { useSettings } from "../settings/SettingsProvider";
import "./map.css";
export function MapHost({ children }: { children?: ReactNode }) {
  const { settings } = useSettings();
  const container = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<MapInstance | null>(null);
  const mapRef = useRef<MapInstance | null>(null);
  const [ready, setReady] = useState(false);
  const [styleVersion, setStyleVersion] = useState(0);
  const [mode3d, setMode3d] = useState(false);
  const [camera, setCamera] = useState({ zoom: 10.6, pitch: 0, bearing: 0, center: [77.209, 28.6139] as [number, number] });
  const pickers = useRef(new Set<(point: [number, number]) => void>());
  const api = useMemo<MapApi>(() => ({
    map, ready, styleVersion, mode3d,
    setMode3d: (value) => { setMode3d(value); map?.easeTo({ pitch: value ? 50 : 0, duration: 0 }); if (map?.getLayer("building-3d")) map.setLayoutProperty("building-3d", "visibility", value ? "visible" : "none"); },
    fitGeometry: (coords, opts) => { if (!coords.length || !map) return; const lons = coords.map(([lon]) => lon).filter(Number.isFinite); const lats = coords.map(([, lat]) => lat).filter(Number.isFinite); if (!lons.length || !lats.length) return; const bounds: [[number, number], [number, number]] = [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]]; const span = Math.max(bounds[1][0] - bounds[0][0], bounds[1][1] - bounds[0][1]); const zoom = opts?.maxZoom ? Math.min(opts.maxZoom, span < 0.03 ? 14 : span < 0.12 ? 12 : 10.6) : span < 0.03 ? 14 : span < 0.12 ? 12 : 10.6; map.flyTo({ center: [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2], zoom, duration: 0 }); },
    flyTo: (center, zoom = 15) => map?.flyTo({ center, zoom, duration: 0 }),
    setPickMode: () => undefined,
    onPick: (callback) => { pickers.current.add(callback); return () => pickers.current.delete(callback); },
    registerClickTarget: () => () => undefined,
    addControl: (control) => map?.addControl(control),
    removeControl: (control) => map?.removeControl(control)
  }), [map, ready, styleVersion, mode3d]);
  useEffect(() => {
    if (!container.current) return;
    const instance = new maplibregl.Map({ container: container.current, style: buildStyle(settings.theme, settings.lang), center: [77.209, 28.6139], zoom: 10.6, minZoom: 8, maxZoom: 18.5, maxPitch: 60, maxBounds: [[75.8, 27.6], [78.6, 29.9]], renderWorldCopies: false, attributionControl: false });
    mapRef.current = instance; setMap(instance); instance.resize();
    instance.on("load", () => { setReady(true); window.__naadiSplash?.setStatus("map"); window.__naadiSplash?.hide(); });
    const readiness = window.setInterval(() => { if (instance.isStyleLoaded()) { setReady(true); window.__naadiSplash?.setStatus("map"); window.__naadiSplash?.hide(); window.clearInterval(readiness); } }, 100);
    const initialReady = window.setTimeout(() => { setReady(true); window.__naadiSplash?.setStatus("map"); window.__naadiSplash?.hide(); }, 500);
    instance.on("style.load", () => setStyleVersion((value) => value + 1));
    instance.on("move", () => setCamera({ zoom: instance.getZoom(), pitch: instance.getPitch(), bearing: instance.getBearing(), center: [instance.getCenter().lng, instance.getCenter().lat] }));
    instance.on("click", (event) => pickers.current.forEach((callback) => callback([event.lngLat.lng, event.lngLat.lat])));
    const resize = new ResizeObserver(() => instance.resize()); resize.observe(container.current);
    return () => { window.clearInterval(readiness); window.clearTimeout(initialReady); resize.disconnect(); instance.remove(); mapRef.current = null; setMap(null); };
  }, []);
  useEffect(() => { if (mapRef.current && ready) mapRef.current.setStyle(buildStyle(settings.theme, settings.lang)); }, [settings.theme, settings.lang, ready]);
  return <MapContext.Provider value={api}><div className="map-wrap"><div ref={container} className="map-canvas" data-testid="map" data-control aria-label="Map. Use arrow keys to pan, equals and minus to zoom." data-ready={ready} data-style={settings.theme} data-zoom={camera.zoom.toFixed(2)} data-pitch={Math.round(camera.pitch)} data-bearing={Math.round(camera.bearing)} data-center={`${camera.center[0].toFixed(5)},${camera.center[1].toFixed(5)}`} /></div><div className="map-attribution"><a data-testid="attr-osm" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a> · <a data-testid="attr-ofm" href="https://openfreemap.org/" target="_blank" rel="noopener noreferrer">OpenFreeMap</a> · <a data-testid="attr-omt" href="https://www.openmaptiles.org/" target="_blank" rel="noopener noreferrer">OpenMapTiles</a></div>{children}</MapContext.Provider>;
}
