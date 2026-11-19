import type { JourneyResponse, Leg, OptionBase } from "./types";
export function isJourneyResponse(value: unknown): value is JourneyResponse { if(!value||typeof value!=="object")return false; const v=value as Partial<JourneyResponse>; return Array.isArray(v.options)&&v.options.every(isOption); }
export function isOption(value: unknown): value is OptionBase { if(!value||typeof value!=="object")return false;const v=value as Partial<OptionBase>;return typeof v.total_min==="number"&&Number.isFinite(v.total_min)&&typeof v.arrive==="string"&&Array.isArray(v.legs)&&v.legs.every(isLeg); }
export function isLeg(value: unknown): value is Leg { return Boolean(value&&typeof value==="object"&&typeof (value as {type?:unknown}).type==="string"); }
