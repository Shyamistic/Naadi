import { Outlet, useLocation } from "react-router";
import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { MapHost } from "../map/MapHost";
import { Sheet } from "../components/Sheet";
import css from "./shell.module.css";
import "./sheet.css";
export function AppShell(){const location=useLocation();const documentPage=["/accuracy","/about","/help","/settings"].some(p=>location.pathname.startsWith(p));return <div className={`${css.shell} shell`}><a href="#main" className="skip-link" data-testid="skip-link">Skip to main content</a><AppHeader/><main className="app-content" id="main">{!documentPage&&<div className="map-area"><MapHost/></div>}{documentPage?<section className="panel document-panel"><div className="panel-inner"><Outlet/><Footer/></div></section>:<Sheet><section className="panel"><div className="panel-inner"><Outlet/></div></section></Sheet>}</main></div>}
