import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiPausedUntil, BURST, onApiPause, resetApiClient } from "./client";

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("apiGet", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => { resetApiClient(); fetchMock = vi.fn(async (url: string) => ok({ url })); vi.stubGlobal("fetch", fetchMock); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("shares one request between identical calls in flight", async () => {
    const [a, b] = await Promise.all([apiGet<{ url: string }>("/stops/1/departures"), apiGet<{ url: string }>("/stops/1/departures")]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(a).toEqual(b);
    await apiGet("/stops/1/departures");
    expect(fetchMock).toHaveBeenCalledTimes(2); // finished requests are not cached
  });

  it("lets one caller leave without cancelling the request for the others", async () => {
    const leaving = new AbortController();
    const first = apiGet("/health", { signal: leaving.signal });
    const second = apiGet<{ url: string }>("/health");
    leaving.abort();
    await expect(first).rejects.toMatchObject({ kind: "aborted" });
    await expect(second).resolves.toMatchObject({ url: "/api/health" });
  });

  it("reports a 4xx once, without retrying", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Unknown stop_id." }), { status: 404 }));
    await expect(apiGet("/stops/9/departures")).rejects.toMatchObject({ kind: "http", status: 404, detail: "Unknown stop_id." });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("waits out a 429 and sends the request again", async () => {
    const pauses: number[] = [];
    const stop = onApiPause((until) => pauses.push(until));
    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 429, headers: { "Retry-After": "1" } }));
    const started = Date.now();
    await expect(apiGet<{ url: string }>("/live/buses")).resolves.toMatchObject({ url: "/api/live/buses" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(Date.now() - started).toBeGreaterThanOrEqual(900);
    expect(pauses).toHaveLength(1);
    expect(apiPausedUntil()).toBeGreaterThan(started);
    stop();
  });

  it("holds a runaway burst to the token bucket", async () => {
    const calls = Array.from({ length: BURST + 4 }, (_, index) => apiGet(`/stops/${index}/departures`));
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(BURST);
    await Promise.all(calls);
    expect(fetchMock).toHaveBeenCalledTimes(BURST + 4);
  });
});
