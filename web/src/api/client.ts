import type { ApiError } from "./errors";
export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
export async function apiGet<T>(path: string, options: { signal?: AbortSignal; timeoutMs?: number } = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 15000);
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  try {
    const response = await fetch(`${API_BASE}${path}`, { signal: controller.signal });
    if (!response.ok) {
      let detail: string | undefined;
      try { const body = await response.json() as { detail?: string | { msg?: string }[] }; detail = typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg; } catch { /* empty response */ }
      throw { kind: "http", status: response.status, detail, path } satisfies ApiError;
    }
    return await response.json() as T;
  } catch (error) {
    if (typeof error === "object" && error !== null && "kind" in error) throw error;
    const kind = error instanceof DOMException && error.name === "AbortError" ? "timeout" : "network";
    throw { kind, path } satisfies ApiError;
  } finally { clearTimeout(timeout); options.signal?.removeEventListener("abort", abort); }
}
