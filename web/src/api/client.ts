import type { ApiError } from "./errors";
export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

// The server gives each IP address a budget of requests a minute and answers 429 beyond it. These guards keep a tab
// inside that budget even if a screen misbehaves, and let it carry on by itself when the server does answer 429
// (several people on one office or mobile network share an address):
// 1. identical GETs already in flight share one request;
// 2. a token bucket lets a tab send a burst of BURST requests, then RATE_PER_S a second;
// 3. after a 429 every request waits out the server's Retry-After, and the refused request is sent again.
export const BURST = 40;
export const RATE_PER_S = 4;
const MAX_PAUSE_MS = 60_000;
const RETRIES_AFTER_429 = 2;
const DEFAULT_TIMEOUT_MS = 15_000;

let tokens = BURST;
let refilledAt = Date.now();
let pausedUntil = 0;
const pauseListeners = new Set<(until: number) => void>();
type Shared = { promise: Promise<unknown>; controller: AbortController; waiting: number };
const inFlight = new Map<string, Shared>();

/** The time (ms since the epoch) until which requests wait because the server answered 429; 0 if never. */
export const apiPausedUntil = () => pausedUntil;
export function onApiPause(listener: (until: number) => void): () => void {
  pauseListeners.add(listener);
  return () => { pauseListeners.delete(listener); };
}
/** Test hook: forget pauses, spent tokens and requests in flight. */
export function resetApiClient() { tokens = BURST; refilledAt = Date.now(); pausedUntil = 0; inFlight.clear(); }

function pause(ms: number) {
  const until = Date.now() + Math.min(MAX_PAUSE_MS, Math.max(1000, ms));
  if (until <= pausedUntil) return;
  pausedUntil = until;
  pauseListeners.forEach((listener) => listener(until));
}
function retryAfterMs(response: Response) {
  const header = response.headers.get("Retry-After");
  const seconds = Number(header);
  if (header && Number.isFinite(seconds)) return seconds * 1000;
  const date = header ? Date.parse(header) : NaN;
  return Number.isFinite(date) ? date - Date.now() : 10_000;
}
function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
    const stop = () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, ms);
    signal.addEventListener("abort", stop, { once: true });
  });
}
async function takeTurn(signal: AbortSignal) {
  for (;;) {
    const now = Date.now();
    tokens = Math.min(BURST, tokens + (now - refilledAt) / 1000 * RATE_PER_S);
    refilledAt = now;
    const wait = Math.max(pausedUntil - now, tokens >= 1 ? 0 : (1 - tokens) / RATE_PER_S * 1000);
    if (wait <= 0) { tokens -= 1; return; }
    await sleep(Math.ceil(wait), signal);
  }
}

async function send<T>(path: string, signal: AbortSignal, timeoutMs: number): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    try { await takeTurn(signal); } catch { throw { kind: "aborted", path } satisfies ApiError; }
    const controller = new AbortController();
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    try {
      const response = await fetch(`${API_BASE}${path}`, { signal: controller.signal });
      if (response.status === 429) {
        const wait = retryAfterMs(response);
        pause(wait);
        if (attempt < RETRIES_AFTER_429) continue;
        throw { kind: "http", status: 429, detail: "Too many requests", path, retryAfterS: Math.ceil(wait / 1000) } satisfies ApiError;
      }
      if (!response.ok) {
        let detail: string | undefined;
        try { const body = await response.json() as { detail?: string | { msg?: string }[] }; detail = typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg; } catch { /* empty response */ }
        throw { kind: "http", status: response.status, detail, path } satisfies ApiError;
      }
      return await response.json() as T;
    } catch (error) {
      if (typeof error === "object" && error !== null && "kind" in error) throw error;
      if (signal.aborted) throw { kind: "aborted", path } satisfies ApiError;
      throw { kind: timedOut ? "timeout" : "network", path } satisfies ApiError;
    } finally { clearTimeout(timeout); signal.removeEventListener("abort", abort); }
  }
}

/** GET an API path (e.g. "/stops/10046/departures"). Rejects with an ApiError. Aborting `signal` only detaches
 *  this caller; the shared request is cancelled once every caller waiting for it has gone. */
export function apiGet<T>(path: string, options: { signal?: AbortSignal; timeoutMs?: number } = {}): Promise<T> {
  const { signal } = options;
  if (signal?.aborted) return Promise.reject({ kind: "aborted", path } satisfies ApiError);
  let entry = inFlight.get(path);
  if (!entry) {
    const created: Shared = { controller: new AbortController(), waiting: 0, promise: Promise.resolve() };
    created.promise = send<T>(path, created.controller.signal, options.timeoutMs ?? DEFAULT_TIMEOUT_MS).finally(() => { if (inFlight.get(path) === created) inFlight.delete(path); });
    inFlight.set(path, created);
    entry = created;
  }
  const shared = entry;
  shared.waiting += 1;
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const leave = () => { if (settled) return false; settled = true; shared.waiting -= 1; signal?.removeEventListener("abort", onAbort); return true; };
    function onAbort() {
      if (!leave()) return;
      if (shared.waiting <= 0) { if (inFlight.get(path) === shared) inFlight.delete(path); shared.controller.abort(); }
      reject({ kind: "aborted", path } satisfies ApiError);
    }
    signal?.addEventListener("abort", onAbort, { once: true });
    shared.promise.then((value) => { if (leave()) resolve(value as T); }, (error: unknown) => { if (leave()) reject(error); });
  });
}
