import { describe, expect, it } from "vitest";
import { buildStyle } from "./base";
describe("basemap styles",()=>{it.each(["light","dark"] as const)("has valid unique layers for %s",theme=>{const style=buildStyle(theme);const ids=style.layers.map(l=>l.id);expect(ids.every(Boolean)).toBe(true);expect(new Set(ids).size).toBe(ids.length);expect(ids.indexOf("label-road")).toBeGreaterThan(-1);});});
