import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Lang } from "../i18n";
export type Theme = "light" | "dark";
export type TextSize = 100 | 112 | 125;
export type Settings = { lang: Lang; theme: Theme; textSize: TextSize; reduceMotion: boolean; includeMetro: boolean };
export const defaultSettings: Settings = { lang: "en", theme: "light", textSize: 100, reduceMotion: false, includeMetro: true };
const KEY = "naadi.settings.v1";
export function readSettings(): Settings { try { const value = JSON.parse(localStorage.getItem(KEY) || "null") as Partial<Settings> | null; return { ...defaultSettings, ...value, lang: value?.lang === "hi" ? "hi" : "en", theme: value?.theme === "dark" ? "dark" : "light", textSize: value?.textSize === 112 || value?.textSize === 125 ? value.textSize : 100 }; } catch { return defaultSettings; } }
export function writeSettings(settings: Settings) { try { localStorage.setItem(KEY, JSON.stringify(settings)); } catch { /* storage is optional */ } }
const SettingsContext = createContext<{ settings: Settings; update: (patch: Partial<Settings>) => void; reset: () => void }>({ settings: defaultSettings, update: () => undefined, reset: () => undefined });
export function SettingsProvider({ children }: { children: ReactNode }) { const [settings, setSettings] = useState(readSettings); useEffect(() => { writeSettings(settings); const root = document.documentElement; root.dataset.theme = settings.theme; root.lang = settings.lang; root.dataset.textSize = String(settings.textSize); root.dataset.reducedMotion = String(settings.reduceMotion || matchMedia("(prefers-reduced-motion: reduce)").matches); }, [settings]); const value = useMemo(() => ({ settings, update: (patch: Partial<Settings>) => setSettings((old) => ({ ...old, ...patch })), reset: () => setSettings(defaultSettings) }), [settings]); return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>; }
export function useSettings() { return useContext(SettingsContext); }
