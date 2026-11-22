import { test, expect, type Page } from '@playwright/test';

// Real-data checks (tag @live), run with playwright.live.config.ts: through `vite preview` against the live API, or
// straight against a deployed site with NAADI_BASE_URL=https://13-235-147-97.sslip.io. Each screen stays open for
// a while; the test fails on any 429 or 5xx, on a screen that keeps re-fetching, and on uncaught page errors.

type Hit = { path: string; status?: number };
function watch(page: Page) {
  const hits: Hit[] = []; const failures: string[] = []; const errors: string[] = [];
  page.on('request', (request) => { const url = new URL(request.url()); if (url.pathname.startsWith('/api/')) hits.push({ path: url.pathname.slice(4) + url.search }); });
  page.on('response', (response) => { const url = new URL(response.url()); if (url.pathname.startsWith('/api/') && (response.status() === 429 || response.status() >= 500)) failures.push(`${response.status()} ${url.pathname}`); });
  page.on('pageerror', (error) => errors.push(error.message));
  return { hits, failures, errors };
}
function expectCalm({ hits, failures, errors }: ReturnType<typeof watch>, label: string, perEndpoint = 3) {
  const counts = new Map<string, number>();
  for (const hit of hits) { const path = hit.path.split('?')[0]; counts.set(path, (counts.get(path) ?? 0) + 1); }
  const summary = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([path, count]) => `${path} ×${count}`).join(', ');
  expect(failures, `${label}: refused or failed API calls (${summary})`).toEqual([]);
  expect(errors, `${label}: page errors`).toEqual([]);
  for (const [path, count] of counts) expect(count, `${label}: ${path} ×${count} (${summary})`).toBeLessThanOrEqual(perEndpoint);
}
async function loaded(page: Page) { await expect(page.locator('#splash')).toHaveCount(0, { timeout: 20_000 }); }
async function openNav(page: Page, id: 'live' | 'speeds') {
  const link = page.getByTestId(`nav-${id}`);
  if (await link.isVisible()) return link.click();
  await page.getByTestId('header-menu').click();
  await page.getByTestId(`drawer-${id}`).click();
}

const PLAN = '/?from=28.667500,77.228200&fromName=Kashmere+Gate&to=28.549100,77.253300&toName=Nehru+Place&depart=2026-11-24T08:30&modes=bus,metro,rail,shared_auto';
const screens: Array<[string, RegExp]> = [
  ['/', /Plan a bus journey|बस यात्रा/], ['/live', /Live buses|लाइव बसें/], ['/speeds', /Road speeds|सड़क/], ['/accuracy', /accurate|सटीक/], ['/about', /About|बारे/],
  ['/stop/10046', /.+/], ['/stop/817', /.+/], ['/route/1468', /Route|रूट/], [PLAN, /.+/],
];

test.describe('live data @live', () => {
  test.describe.configure({ timeout: 120_000 });
  for (const [path, heading] of screens) test(`${path.slice(0, 40)} loads and settles @live`, async ({ page }) => {
    const seen = watch(page);
    await page.goto(path);
    await loaded(page);
    await expect(page.locator('h1').first()).toContainText(heading, { timeout: 30_000 });
    await page.waitForTimeout(15_000);
    expectCalm(seen, path);
  });

  // The path reported on 22 Nov: Live buses, a route number, a stop on that route (Gandhi Darshan), then back.
  for (const lang of ['en', 'hi'] as const) test(`live → route → stop → live → speeds (${lang}) @live`, async ({ page }) => {
    if (lang === 'hi') await page.addInitScript(() => localStorage.setItem('naadi.settings.v1', JSON.stringify({ lang: 'hi' })));
    const seen = watch(page);
    await page.goto('/live');
    await loaded(page);
    await page.getByTestId('live-route-link-0').click();
    await expect(page).toHaveURL(/\/route\/\d+$/, { timeout: 20_000 });
    await expect(page.locator('h1')).toContainText(/Route|रूट/, { timeout: 30_000 });
    const gandhi = page.getByRole('link', { name: /Gandhi Darshan/ });
    await ((await gandhi.count()) ? gandhi.first() : page.getByTestId('route-stop-2')).click();
    await expect(page).toHaveURL(/\/stop\/\d+$/);
    await expect(page.getByTestId('departure-row-0').or(page.getByText('No buses expected in the next 45 minutes'))).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(35_000); // one 30 s refresh
    expectCalm(seen, 'stop page after live → route', 4);
    await openNav(page, 'live');
    await expect(page.getByTestId('live-route-link-0')).toBeVisible({ timeout: 30_000 });
    await openNav(page, 'speeds');
    await expect(page.getByTestId('speeds-daytype')).toBeVisible({ timeout: 30_000 }); // only drawn once the cells load
    await expect(page.getByText('Road speeds are unavailable')).toHaveCount(0);
    expectCalm(seen, `whole flow (${lang})`, 6);
  });

  test('Gandhi Darshan from route 1468 @live', async ({ page }) => {
    const seen = watch(page);
    await page.goto('/route/1468');
    await loaded(page);
    await expect(page.locator('h1')).toContainText(/Route|रूट/, { timeout: 30_000 });
    const gandhi = page.getByRole('link', { name: /Gandhi Darshan/ });
    test.skip(!(await gandhi.count()), 'route 1468 has no Gandhi Darshan stop');
    await gandhi.first().click();
    await expect(page.locator('h1')).toContainText(/Gandhi Darshan/, { timeout: 30_000 });
    await page.waitForTimeout(20_000);
    expectCalm(seen, 'Gandhi Darshan');
  });
});
