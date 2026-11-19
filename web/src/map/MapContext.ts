import { createContext, useContext } from "react";
import type maplibregl from "maplibre-gl";
export type MapGeoJSONFeature={id?:string|number;properties?:Record<string,unknown>};
export type MapApi={map:maplibregl.Map|null;ready:boolean;styleVersion:number;mode3d:boolean;setMode3d:(v:boolean)=>void;fitGeometry:(coords:[number,number][],opts?:{padding?:number;maxZoom?:number})=>void;flyTo:(center:[number,number],zoom?:number)=>void;setPickMode:(kind:"from"|"to"|null)=>void;onPick:(cb:(lngLat:[number,number])=>void)=>()=>void;registerClickTarget:(layerId:string,priority:number,handler:(feature:MapGeoJSONFeature,lngLat:[number,number])=>void)=>()=>void};
export const MapContext=createContext<MapApi>({map:null,ready:false,styleVersion:0,mode3d:false,setMode3d:()=>undefined,fitGeometry:()=>undefined,flyTo:()=>undefined,setPickMode:()=>undefined,onPick:()=>()=>undefined,registerClickTarget:()=>()=>undefined});
export const useMap=()=>useContext(MapContext);
