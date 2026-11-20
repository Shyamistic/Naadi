import { createContext, useContext, useMemo, type ReactNode } from "react";
import { translate, type Lang, type TranslationKey, type TranslationVars } from "./index";
const I18nContext = createContext<{ lang: Lang; t: (key: TranslationKey, vars?: TranslationVars) => string }>({ lang: "en", t: (key) => translate("en", key) });
export function I18nProvider({ lang, children }: { lang: Lang; children: ReactNode }) { const value = useMemo(() => ({ lang, t: (key: TranslationKey, vars?: TranslationVars) => translate(lang, key, vars) }), [lang]); return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>; }
export function useT() { return useContext(I18nContext); }
