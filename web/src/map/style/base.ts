import type { StyleSpecification } from "maplibre-gl";
import { palettes } from "./palettes";
const nameExpression=["coalesce",["get","name:hi"],["get","name:en"],["get","name_en"],["get","name"]] as unknown as string[];
export function buildStyle(theme:"light"|"dark", language:"en"|"hi"="en"):StyleSpecification{const p=palettes[theme];const label=language==="hi"?nameExpression:["coalesce",["get","name:en"],["get","name_en"],["get","name"]];return ({version:8,glyphs:"https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",sources:{omt:{type:"vector",url:"https://tiles.openfreemap.org/planet"}},layers:[
{id:"background",type:"background",paint:{"background-color":p.background}},
{id:"landuse-residential",type:"fill",source:"omt", "source-layer":"landuse",minzoom:10,filter:["in","class","residential","suburb","neighbourhood"],paint:{"fill-color":p.residential}},
{id:"landcover-green",type:"fill",source:"omt","source-layer":"landcover",filter:["in","class","wood","grass","wetland"],paint:{"fill-color":p.green}},
{id:"park",type:"fill",source:"omt","source-layer":"park",paint:{"fill-color":p.park}},
{id:"water",type:"fill",source:"omt","source-layer":"water",paint:{"fill-color":p.water}},
{id:"waterway",type:"line",source:"omt","source-layer":"waterway",minzoom:8,filter:["in","class","river","canal","stream"],paint:{"line-color":p.waterway,"line-width":["interpolate",["linear"],["zoom"],10,1,16,3]}},
{id:"building",type:"fill",source:"omt","source-layer":"building",minzoom:14,paint:{"fill-color":p.building,"fill-outline-color":p.roadCasing}},
...(["minor","secondary","primary","major"] as const).flatMap((kind,i)=>[{id:`road-casing-${kind}`,type:"line" as const,source:"omt", "source-layer":"transportation",minzoom:i===0?13:i===1?10:i===2?8:6,filter:["==","class",kind],paint:{"line-color":p.roadCasing,"line-width":["interpolate",["linear"],["zoom"],8,1,14,6,18,18]}},{id:`road-${kind}`,type:"line" as const,source:"omt","source-layer":"transportation",minzoom:i===0?13:i===1?10:i===2?8:6,filter:["==","class",kind],paint:{"line-color":kind==="major"?p.major:p.road,"line-width":["interpolate",["linear"],["zoom"],8,0.6,14,4,18,16]}}]),
{id:"road-path",type:"line",source:"omt","source-layer":"transportation",minzoom:15,filter:["in","class","path","track"],paint:{"line-color":p.roadCasing,"line-dasharray":[2,2],"line-width":1}},
{id:"rail",type:"line",source:"omt","source-layer":"transportation",minzoom:10,filter:["==","class","rail"],paint:{"line-color":p.roadCasing,"line-dasharray":[3,3],"line-width":1}},
{id:"transit",type:"line",source:"omt","source-layer":"transportation",minzoom:10,filter:["==","class","transit"],paint:{"line-color":p.muted,"line-width":1.5}},
{id:"boundary-state",type:"line",source:"omt","source-layer":"boundary",minzoom:6,filter:["==","admin_level",4],paint:{"line-color":p.roadCasing,"line-dasharray":[4,3],"line-width":1}},
{id:"building-3d",type:"fill-extrusion",source:"omt","source-layer":"building",minzoom:14,layout:{visibility:"none"},paint:{"fill-extrusion-color":p.building,"fill-extrusion-height":["coalesce",["get","render_height"],0],"fill-extrusion-base":["coalesce",["get","render_min_height"],0],"fill-extrusion-opacity":.9}},
{id:"label-road",type:"symbol",source:"omt","source-layer":"transportation_name",minzoom:13,layout:{"symbol-placement":"line","text-field":label,"text-size":["interpolate",["linear"],["zoom"],13,11,18,13],"text-font":["Noto Sans Regular"]},paint:{"text-color":p.muted,"text-halo-color":p.halo,"text-halo-width":1.2}},
{id:"label-waterway",type:"symbol",source:"omt","source-layer":"waterway",minzoom:12,filter:["has","name"],layout:{"symbol-placement":"line","text-field":label,"text-font":["Noto Sans Italic"],"text-size":12},paint:{"text-color":p.waterway}},
{id:"label-transit",type:"symbol",source:"omt","source-layer":"poi",minzoom:14,filter:["==","class","railway"],layout:{"text-field":label,"text-font":["Noto Sans Regular"],"text-size":11},paint:{"text-color":p.muted}},
{id:"label-place-minor",type:"symbol",source:"omt","source-layer":"place",minzoom:12,filter:["in","class","suburb","neighbourhood","quarter"],layout:{"text-field":label,"text-font":["Noto Sans Regular"],"text-size":12},paint:{"text-color":p.muted}},
{id:"label-place-major",type:"symbol",source:"omt","source-layer":"place",minzoom:8,filter:["in","class","city","town","village"],layout:{"text-field":label,"text-font":["Noto Sans Bold"],"text-size":15},paint:{"text-color":p.text,"text-halo-color":p.halo,"text-halo-width":1}}
]} as unknown as StyleSpecification);}

