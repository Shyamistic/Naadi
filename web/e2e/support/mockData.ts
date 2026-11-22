import type { Page, Route } from '@playwright/test';

// A small, internally consistent slice of the API (one route, three stops, two live buses) so the screens render
// their normal, loaded state. mockApi() answers 404 for most endpoints, which only exercises the error states.
const hours = (value: number) => Array.from({ length: 24 }, () => value);
const feedTime = () => new Date().toISOString();

const stops = [
  { stop_id: 10045, name: 'Rajghat', lat: 28.6421, lon: 77.2478 },
  { stop_id: 10046, name: 'Gandhi Darshan', lat: 28.6407, lon: 77.2495 },
  { stop_id: 817, name: 'Delhi Gate', lat: 28.639, lon: 77.241 },
];
const route = {
  route_id: 1468, route: '405', variant: '405UP', from: 'Kashmere Gate', towards: 'Mehrauli', agency: 'DTC', opposite_route_id: null,
  day_type: 'weekday', hour: 12,
  stops: stops.map((stop, index) => ({ ...stop, ord: index + 1, dist_m: index * 600, min_from_start: index * 2.5 })),
  geometry: stops.map((stop) => [stop.lon, stop.lat]),
  hourly: { weekday: { end_to_end_min: hours(42), buses_per_hour: hours(6) }, weekend: { end_to_end_min: hours(38), buses_per_hour: hours(4) } },
  attribution: 'fixture',
};
const departures = (stop: (typeof stops)[number]) => ({
  stop, now: feedTime(), attribution: 'fixture',
  departures: [
    { route: '405', route_variant: '405UP', route_id: 1468, towards: 'Mehrauli', live_eta_min: [3.2, 14.8], typical_wait_min: 7.5 },
    { route: '423', route_variant: '423DOWN', route_id: 1500, towards: 'Kashmere Gate', live_eta_min: [], typical_wait_min: 12 },
  ],
});

export type Handler = (route: Route, url: URL) => Promise<void> | void;
const json = (route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) => route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(body) });

/** Serves the fixture API. `override` runs first and can answer any request itself (return true when it did). */
export async function mockApiData(page: Page, override?: (route: Route, url: URL) => Promise<boolean> | boolean) {
  await page.route('**/api/**', async (request) => {
    const url = new URL(request.request().url());
    if (override && await override(request, url)) return;
    const path = url.pathname.replace(/^\/api/, '');
    if (path === '/health') return json(request, { status: 'ok', live: { buses: 2, on_route: 2, feed_ts: Date.now() / 1000 } });
    if (path === '/capabilities') return json(request, { web_api_version: 1 });
    if (path === '/stops/all') return json(request, { fields: ['stop_id', 'name', 'lat', 'lon', 'routes'], count: stops.length, stops: stops.map((stop) => [stop.stop_id, stop.name, stop.lat, stop.lon, 2]) }, 200, { 'Cache-Control': 'public, max-age=86400' });
    const stopMatch = path.match(/^\/stops\/(\d+)\/departures$/);
    if (stopMatch) { const stop = stops.find((item) => item.stop_id === Number(stopMatch[1])); return stop ? json(request, departures(stop)) : json(request, { detail: 'Unknown stop_id.' }, 404); }
    if (path === '/routes/search') return json(request, { query: url.searchParams.get('q'), routes: [{ route: '405', variants: [{ route_id: 1468, variant: '405UP', from: 'Kashmere Gate', towards: 'Mehrauli', stops: 3, agency: 'DTC' }] }] });
    if (path === '/routes/1468') return json(request, route);
    if (path === '/live/buses') {
      const buses = [[1468, '405', '405UP', 28.6412, 77.2488, 20, 300.5], [1500, '423', '423DOWN', 28.65, 77.23, 45, null]];
      const selected = url.searchParams.get('route_id');
      const rows = selected ? buses.filter((bus) => String(bus[0]) === selected) : buses;
      return json(request, { feed_time: feedTime(), count: rows.length, fields: ['route_id', 'route', 'variant', 'lat', 'lon', 'age_s', 'progress_m'], buses: rows });
    }
    if (path === '/speeds/cells') return json(request, { cells: [{ lat: 28.63, lon: 77.22, weekday: hours(18), weekend: hours(22), n: 120 }, { lat: 28.6, lon: 77.2, weekday: hours(12), weekend: hours(16), n: 80 }], source: 'fixture' });
    if (path === '/pulse') return json(request, { feed_time: feedTime(), stale: false, buses: 2, on_route: 2, window_min: 30, traversals: 40, hour: 12, day_type: 'weekday', vs_usual: { ratio: 1.04, pct: 4 }, slow: [], density: [[28.64, 77.24, 2]] });
    return json(request, { detail: `No fixture for ${path}` }, 404);
  });
  await page.route('https://photon.komoot.io/**', (request) => request.fulfill({ contentType: 'application/json', body: JSON.stringify({ type: 'FeatureCollection', features: [] }) }));
}
