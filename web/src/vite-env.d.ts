/// <reference types="vite/client" />
declare global { interface Window { __naadiReady?: boolean; __naadiSplash?: { setStatus:(key:string)=>void; hide:()=>void } } }
export {};
