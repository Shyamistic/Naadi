import type { Page } from '@playwright/test';

export async function mockApi(page: Page, scenario: { health?: 'live' | 'down' } = {}) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    if (scenario.health === 'down' && url.pathname.endsWith('/health')) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'unavailable' }) });
    if (url.pathname.endsWith('/health')) return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok', buses: 5398, feed_ts: new Date().toISOString() }) });
    if (url.pathname.endsWith('/capabilities')) return route.fulfill({ contentType: 'application/json', body: JSON.stringify({}) });
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: `No fixture for ${url.pathname}` }) });
  });
  await page.route('https://photon.komoot.io/**', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ type: 'FeatureCollection', features: [] }) }));
}
