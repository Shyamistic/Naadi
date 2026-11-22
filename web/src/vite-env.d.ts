/// <reference types="vite/client" />
declare global { const __NAADI_BUILD__: string; interface Window { __naadiReady?: boolean; __naadiSplash?: { setStatus:(key:string)=>void; hide:()=>void } } }
export {};
