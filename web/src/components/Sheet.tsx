import { useEffect, useState, type ReactNode } from "react";
export type Snap="peek"|"half"|"full";
const heights:Record<Snap,string>={peek:"9rem",half:"52dvh",full:"calc(100dvh - var(--header-h) - 8px)"};
export function Sheet({children}:{children:ReactNode}){const [snap,setSnap]=useState<Snap>("peek");useEffect(()=>{document.documentElement.style.setProperty("--sheet-h",heights[snap]);return()=>{document.documentElement.style.removeProperty("--sheet-h")}},[snap]);const next=snap==="peek"?"half":snap==="half"?"full":"half";return <section className="sheet" data-snap={snap}><button className="sheet-handle" data-testid="sheet-handle" aria-expanded={snap!=="peek"} onClick={()=>setSnap(next)}><span/></button><div className="sheet-content">{children}</div></section>}
