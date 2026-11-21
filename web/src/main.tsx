import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./styles/base.css";
import "./styles/ui.css";
import "./styles/print.css";
import { SettingsProvider, useSettings } from "./settings/SettingsProvider";
import { I18nProvider } from "./i18n/I18nProvider";
import { AppRouter } from "./app/router";
import { ErrorBoundary } from "./components/ErrorBoundary";
function Providers(){const {settings}=useSettings();return <I18nProvider lang={settings.lang}><ErrorBoundary><AppRouter/></ErrorBoundary></I18nProvider>}
const client=new QueryClient({defaultOptions:{queries:{retry:1,refetchOnWindowFocus:false,staleTime:30_000}}});
createRoot(document.getElementById("root")!).render(<StrictMode><QueryClientProvider client={client}><SettingsProvider><Providers/></SettingsProvider></QueryClientProvider></StrictMode>);
