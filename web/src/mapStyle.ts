// "Dilli dusk": a dark vector style over OpenFreeMap tiles (OpenMapTiles schema, no API key).
import type { StyleSpecification } from "maplibre-gl";

const road = (cls: string[], color: string, w: [number, number, number, number]): any => ({
  type: "line", source: "omt", "source-layer": "transportation",
  filter: ["in", ["get", "class"], ["literal", cls]],
  layout: { "line-cap": "round", "line-join": "round" },
  paint: { "line-color": color, "line-width": ["interpolate", ["exponential", 1.5], ["zoom"], w[0], w[1], w[2], w[3]] },
});

export const duskStyle: StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: { omt: { type: "vector", url: "https://tiles.openfreemap.org/planet" } },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#0a0f24" } },
    { id: "park", type: "fill", source: "omt", "source-layer": "park", paint: { "fill-color": "#0d2a22", "fill-opacity": 0.8 } },
    { id: "landcover", type: "fill", source: "omt", "source-layer": "landcover",
      filter: ["in", ["get", "class"], ["literal", ["grass", "wood", "farmland"]]], paint: { "fill-color": "#0c241f", "fill-opacity": 0.6 } },
    { id: "water", type: "fill", source: "omt", "source-layer": "water", paint: { "fill-color": "#0b2547" } },
    { id: "river", type: "line", source: "omt", "source-layer": "waterway", paint: { "line-color": "#11325e", "line-width": 1.2 } },
    road(["minor", "service", "track"], "#1a2240", [12, 0.4, 18, 8]),
    road(["tertiary", "secondary"], "#26305a", [8, 0.5, 18, 14]),
    road(["primary", "trunk"], "#34407a", [6, 0.6, 18, 18]),
    road(["motorway"], "#4a4f8f", [5, 0.8, 18, 22]),
    { id: "rail", type: "line", source: "omt", "source-layer": "transportation", filter: ["==", ["get", "class"], "rail"],
      paint: { "line-color": "#3b2f5c", "line-width": 1, "line-dasharray": [3, 3] } },
    { id: "buildings3d", type: "fill-extrusion", source: "omt", "source-layer": "building", minzoom: 13,
      paint: { "fill-extrusion-color": ["interpolate", ["linear"], ["coalesce", ["get", "render_height"], 6], 0, "#1b2248", 30, "#2c3470", 80, "#4a3f7a"],
        "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6], "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.85 } },
    { id: "road-label", type: "symbol", source: "omt", "source-layer": "transportation_name", minzoom: 13,
      layout: { "symbol-placement": "line", "text-field": ["coalesce", ["get", "name:en"], ["get", "name"]], "text-font": ["Noto Sans Regular"], "text-size": 11 },
      paint: { "text-color": "#8a93c4", "text-halo-color": "#0a0f24", "text-halo-width": 1.2 } },
    { id: "place-label", type: "symbol", source: "omt", "source-layer": "place",
      filter: ["in", ["get", "class"], ["literal", ["city", "town", "suburb", "neighbourhood", "quarter"]]],
      layout: { "text-field": ["coalesce", ["get", "name:en"], ["get", "name"]], "text-font": ["Noto Sans Bold"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 9, 11, 14, 15], "text-transform": "uppercase", "text-letter-spacing": 0.08 },
      paint: { "text-color": "#c7cdf2", "text-halo-color": "#0a0f24", "text-halo-width": 1.5 } },
  ],
};
