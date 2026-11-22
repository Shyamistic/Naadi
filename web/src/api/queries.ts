import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";
import type { AccuracySummary, About, Capabilities, Health, JourneyResponse, LegNextBuses, LiveBuses, Pulse, RouteDetail, RouteSearch, SpeedCells, StopSearchResult, StopsAll, StopsNearby } from "./types";
// Every query passes react-query's signal on, so a screen that closes cancels the requests it no longer needs.
// Polling (refetchInterval) pauses while the tab is hidden.
export const usePulse=()=>useQuery({queryKey:["pulse"],queryFn:({signal})=>apiGet<Pulse>("/pulse",{signal}),refetchInterval:30000,staleTime:15000,retry:1});
export const useHealth=()=>useQuery({queryKey:["health"],queryFn:({signal})=>apiGet<Health>("/health",{signal}),refetchInterval:60000,staleTime:30000});
export const useCapabilities=()=>useQuery({queryKey:["capabilities"],queryFn:({signal})=>apiGet<Capabilities>("/capabilities",{signal}),staleTime:Infinity,retry:false});
export const useStopSearch=(q:string)=>useQuery({queryKey:["stops-search",q],queryFn:({signal})=>apiGet<StopSearchResult>(`/stops/search?q=${encodeURIComponent(q)}&limit=6`,{signal}),enabled:q.trim().length>=2,staleTime:300000});
export const useJourneys=(params:string)=>useQuery({queryKey:["journeys",params],queryFn:({signal})=>apiGet<JourneyResponse>(`/journeys?${params}`,{signal,timeoutMs:30000}),enabled:Boolean(params),retry:false});
export const useRouteSearch=(q:string)=>useQuery({queryKey:["route-search",q],queryFn:({signal})=>apiGet<RouteSearch>(`/routes/search?q=${encodeURIComponent(q)}`,{signal}),enabled:q.length>0,staleTime:600000});
export const useRouteDetail=(id:string,dayType="weekday",hour=12)=>useQuery({queryKey:["route",id,dayType,hour],queryFn:({signal})=>apiGet<RouteDetail>(`/routes/${id}?day_type=${dayType}&hour=${hour}`,{signal}),staleTime:600000});
export const useLiveBuses=(route?:string)=>useQuery({queryKey:["live",route],queryFn:({signal})=>apiGet<LiveBuses>(`/live/buses${route?`?route_id=${route}`:""}`,{signal}),refetchInterval:15000});
// Pages that are nothing without their data keep trying every 30 s after a failure, so they recover on their own.
const retryWhileFailed=(query:{state:{status:string}})=>query.state.status==="error"?30000:false;
export const useSpeedCells=()=>useQuery({queryKey:["cells"],queryFn:({signal})=>apiGet<SpeedCells>("/speeds/cells",{signal}),staleTime:Infinity,refetchInterval:retryWhileFailed});
export const useAccuracy=()=>useQuery({queryKey:["accuracy"],queryFn:({signal})=>apiGet<AccuracySummary>("/accuracy",{signal}),staleTime:600000,refetchInterval:retryWhileFailed});
export const useAbout=()=>useQuery({queryKey:["about"],queryFn:({signal})=>apiGet<About>("/about",{signal}),staleTime:Infinity});
export const useStopsAll=()=>useQuery({queryKey:["stops-all"],queryFn:({signal})=>apiGet<StopsAll>("/stops/all",{signal}),staleTime:Infinity});
export const useNearby=(lat:number,lon:number)=>useQuery({queryKey:["nearby",lat.toFixed(4),lon.toFixed(4)],queryFn:({signal})=>apiGet<StopsNearby>(`/stops/nearby?lat=${lat}&lon=${lon}&radius_m=600&limit=5`,{signal}),enabled:Boolean(lat&&lon),staleTime:300000});
export const useLegNextBuses=(board:number|string,alight:number|string,enabled=true)=>useQuery({queryKey:["leg-next",board,alight],queryFn:({signal})=>apiGet<LegNextBuses>(`/legs/next-buses?board=${board}&alight=${alight}`,{signal}),enabled,refetchInterval:20000});
