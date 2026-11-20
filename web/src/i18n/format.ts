import type { Lang } from "./index";
export const fmtMin = (n: number, lang: Lang = "en") => `${Math.round(n)} ${lang === "hi" ? "मिनट" : "min"}`;
export const fmtDistance = (m: number, lang: Lang = "en") => m >= 1000 ? `${(m / 1000).toFixed(1)} ${lang === "hi" ? "किमी" : "km"}` : `${Math.round(m)} ${lang === "hi" ? "मी" : "m"}`;
export const fmtCount = (n: number) => new Intl.NumberFormat("en-IN").format(n);
export const fmtInr = (n: number | null | undefined) => n == null ? "—" : `₹${Math.round(n)}`;
export const fmtDay = (date: Date | string, lang: Lang = "en") => new Intl.DateTimeFormat(lang === "hi" ? "hi-IN" : "en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short" }).format(typeof date === "string" ? new Date(date) : date);
