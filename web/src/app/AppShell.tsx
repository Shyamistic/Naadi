import { Outlet, useLocation } from "react-router";
import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { MapControls } from "../components/MapControls";
import { MapHost } from "../map/MapHost";
import css from "./shell.module.css";
export function AppShell(){const location=useLocation();const documentPage=["/accuracy","/about","/help","/settings"].some(p=>location.pathname.startsWith(p));return <div className={`${css.shell} shell`}><a href="#main" className="skip-link" data-testid="skip-link">Skip to main content</a><AppHeader/><main className="app-content" id="main">{!documentPage&&<div className="map-area"><MapHost/><MapControls/></div>}<section className={`panel ${documentPage?"document-panel":""}`}><div className="panel-inner"><Outlet/>{documentPage&&<Footer/>}</div></section></main></div>}
