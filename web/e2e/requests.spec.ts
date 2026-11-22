import { test, expect, type Page } from '@playwright/test';
import { mockApiData } from './support/mockData';

// A screen may load its data once and then poll: live buses every 15 s, departures and the city pulse every 30 s,
// health every 60 s. A screen that keeps re-fetching floods the server, which then answers 429 to every screen
// (22 Nov: the stop page sent over 1,300 requests and Live buses and Road speeds stopped working). These tests
// count the /api requests a screen sends while it stays open, on the loaded state and on the error state.

type Hit = { path: string; at: number };
function recordApi(page: Page) {
  const hits: Hit[] = [];
  page.on('request', (request) => { const url = new URL(request.url()); if (url.pathname.startsWith('/api/')) hits.push({ path: url.pathname.slice(4) + url.search, at: Date.now() }); });
  return hits;
}
const endpoint = (path: string) => path.split('?')[0];
function expectCalm(hits: Hit[], { total, perEndpoint, label }: { total: number; perEndpoint: number; label: string }) {
  const counts = new Map<string, number>();
  for (const hit of hits) counts.set(endpoint(hit.path), (counts.get(endpoint(hit.path)) ?? 0) + 1);
  const busiest = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const summary = busiest.slice(0, 6).map(([path, count]) => `${path} ×${count}`).join(', ');
  expect(hits.length, `${label}: ${hits.length} API requests (${summary})`).toBeLessThanOrEqual(total);
  for (const [path, count] of busiest) expect(count, `${label}: ${path} requested ${count} times (${summary})`).toBeLessThanOrEqual(perEndpoint);
}
async function loaded(page: Page) { await expect(page.locator('#splash')).toHaveCount(0); }
async function openNav(page: Page, id: 'live' | 'speeds' | 'plan') {
  const link = page.getByTestId(`nav-${id}`);
  if (await link.isVisible()) return link.click();
  await page.getByTestId('header-menu').click();
  await page.getByTestId(`drawer-${id}`).click();
}

const DWELL_MS = 12_000;
const screens: Array<[string, string]> = [
  ['/', 'plan'], ['/live', 'live buses'], ['/speeds', 'road speeds'], ['/accuracy', 'accuracy'], ['/about', 'about'], ['/help', 'help'], ['/settings', 'settings'],
  ['/stop/10046', 'one stop'], ['/stop/10046,817', 'two stops'], ['/stop/999999', 'unknown stop'], ['/route/1468', 'route'], ['/route/77777', 'unknown route'],
];

test.describe('request budget', () => {
  for (const [path, label] of screens) test(`${label} (${path}) settles`, async ({ page }) => {
    await mockApiData(page);
    const hits = recordApi(page);
    await page.goto(path);
    await loaded(page);
    await page.waitForTimeout(DWELL_MS);
    expectCalm(hits, { total: 20, perEndpoint: 3, label: path });
  });

  test('stop page settles when the API fails', async ({ page }) => {
    await mockApiData(page, (route, url) => { if (url.pathname.includes('/departures')) { void route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"boom"}' }); return true; } return false; });
    const hits = recordApi(page);
    await page.goto('/stop/10046');
    await loaded(page);
    await page.waitForTimeout(DWELL_MS);
    expectCalm(hits, { total: 20, perEndpoint: 4, label: 'failing /stop/10046' });
  });

  // The reported path: Live buses, a route number, a stop on that route, then back to Live buses and Road speeds.
  test('live → route → stop → live → speeds keeps working', async ({ page }) => {
    await mockApiData(page);
    const hits = recordApi(page);
    await page.goto('/live');
    await loaded(page);
    await page.getByTestId('live-route-link-0').click();
    await expect(page).toHaveURL(/\/route\/1468$/);
    await expect(page.locator('h1')).toContainText('405');
    await page.getByRole('link', { name: 'Gandhi Darshan' }).click();
    await expect(page).toHaveURL(/\/stop\/10046$/);
    await expect(page.locator('h1')).toHaveText('Gandhi Darshan');
    const atStop = hits.length;
    await page.waitForTimeout(DWELL_MS);
    expectCalm(hits.slice(atStop), { total: 8, perEndpoint: 2, label: 'stop page after arriving from a route' });
    await openNav(page, 'live');
    await expect(page.locator('h1')).toContainText('Live buses');
    await expect(page.getByTestId('live-route-link-0')).toBeVisible();
    await openNav(page, 'speeds');
    await expect(page.locator('h1')).toContainText('Road speeds');
    await expect(page.getByRole('alert')).toHaveCount(0);
  });

  // Several people behind one network address can reach the server's per-address limit. The app must wait and
  // carry on by itself, not show an error until someone reloads the page.
  test('recovers from 429 without a reload', async ({ page }) => {
    let refused = 0;
    await mockApiData(page, (route, url) => {
      if (url.pathname.endsWith('/live/buses') && refused < 2) { refused += 1; void route.fulfill({ status: 429, headers: { 'Retry-After': '2' }, contentType: 'application/json', body: '{"detail":"Too many requests; try again in 2 s."}' }); return true; }
      return false;
    });
    await page.goto('/live');
    // The pause is over in about 4 s, possibly before the boot splash has gone, so look for the notice at once.
    await expect(page.getByTestId('api-busy')).toBeVisible();
    await loaded(page);
    await expect(page.getByTestId('live-route-link-0')).toBeVisible({ timeout: 12_000 });
    await expect(page.getByTestId('api-busy')).toHaveCount(0, { timeout: 5_000 });
    expect(refused).toBe(2);
  });
});
