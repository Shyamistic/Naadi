import { useEffect } from "react";
import type maplibregl from "maplibre-gl";
import { useMap } from "../MapContext";
import type { SpeedCell } from "../../api/types";

export function speedColor(value: number | null) { if (value == null) return "#9CA3AF"; if (value < 10) return "#B2182B"; if (value < 15) return "#E35D31"; if (value < 20) return "#F4A340"; if (value < 25) return "#6BAED6"; return "#2166AC"; }
export function SpeedsOverlay({ cells, day, hour, onCellClick }: { cells: SpeedCell[]; day: "weekday" | "weekend"; hour: number; onCellClick?: (cell: SpeedCell, speed: number | null) => void }) {
  const { map, ready, styleVersion } = useMap();
  useEffect(() => {
    if (!map || !ready) return;
    const sourceId = "naadi-speed-cells";
    const data = { type: "FeatureCollection", features: cells.map((cell, index) => { const speed = cell[day]?.[hour] ?? null; const d = 0.004; return { type: "Feature", id: index, properties: { index, speed, n: cell.n }, geometry: { type: "Polygon", coordinates: [[[cell.lon - d, cell.lat - d], [cell.lon + d, cell.lat - d], [cell.lon + d, cell.lat + d], [cell.lon - d, cell.lat + d], [cell.lon - d, cell.lat - d]]] } }; }) } as GeoJSON.FeatureCollection;
    const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined; if (source) source.setData(data); else map.addSource(sourceId, { type: "geojson", data });
    if (!map.getLayer("naadi-speed-fill")) map.addLayer({ id: "naadi-speed-fill", type: "fill", source: sourceId, paint: { "fill-color": ["case", ["==", ["get", "speed"], null], "#9CA3AF", ["interpolate", ["linear"], ["get", "speed"], 0, "#B2182B", 10, "#E35D31", 15, "#F4A340", 20, "#6BAED6", 25, "#2166AC"], "fill-opacity": 0.68 } });
    if (!map.getLayer("naadi-speed-outline")) map.addLayer({ id: "naadi-speed-outline", type: "line", source: sourceId, paint: { "line-color": "#FFFFFF", "line-opacity": 0.35, "line-width": 0.5 } });
    const click = (event: maplibregl.MapMouseEvent) => { const feature = map.queryRenderedFeatures(event.point, { layers: ["naadi-speed-fill"] })[0]; const index = Number(feature?.properties?.index); const cell = cells[index]; if (cell) onCellClick?.(cell, cell[day]?.[hour] ?? null); };
    map.on("click", click); return () => { map.off("click", click); ["naadi-speed-outline", "naadi-speed-fill"].forEach((id) => { if (map.getLayer(id)) map.removeLayer(id); }); if (map.getSource(sourceId)) map.removeSource(sourceId); };
  }, [cells, day, hour, map, onCellClick, ready, styleVersion]);
  return null;
}
