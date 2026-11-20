import { test, expect, type Page } from '@playwright/test';
import { mkdir, appendFile } from 'node:fs/promises';

async function waitForMapTiles(page: Page) {
  await page.locator('[data-testid="map"]').waitFor({ state: 'visible' });
  await page.waitForFunction(() => Boolean((window as Window & { __naadiMap?: unknown }).__naadiMap));
  await page.evaluate(() => new Promise<void>((resolve) => {
    const map = (window as Window & { __naadiMap?: { once: (event: string, callback: () => void) => void; isStyleLoaded: () => boolean; isSourceLoaded: (id: string) => boolean; areTilesLoaded: () => boolean } }).__naadiMap!;
    const check = () => { if (map.isStyleLoaded() && map.isSourceLoaded('omt') && map.areTilesLoaded()) resolve(); else map.once('idle', check); };
    check();
  }));
  await page.waitForFunction(() => {
    const map = (window as Window & { __naadiMap?: { isStyleLoaded: () => boolean; isSourceLoaded: (id: string) => boolean; areTilesLoaded: () => boolean } }).__naadiMap;
    return Boolean(map?.isStyleLoaded() && map.isSourceLoaded('omt') && map.areTilesLoaded());
  });
  await expect(page.locator('[data-testid="map"]')).toHaveAttribute('data-ready', 'true');
}

const modes = [
  { name: 'light-en', theme: 'light', lang: 'en' },
  { name: 'dark-en', theme: 'dark', lang: 'en' },
  { name: 'light-hi', theme: 'light', lang: 'hi' },
  { name: 'dark-hi', theme: 'dark', lang: 'hi' },
] as const;

test('capture release maps after idle and tile load', async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const tileResponses: string[] = [];
  const browserErrors: string[] = [];
  await mkdir('screenshots', { recursive: true });
  page.on('console', (message) => { if (message.type() === 'error') browserErrors.push(message.text()); });
  page.on('pageerror', (error) => browserErrors.push(error.message));
  page.on('response', (response) => { if (response.url().includes('tiles.openfreemap.org/planet/')) tileResponses.push(`${response.status()} ${response.url()}`); });
  await page.goto('/');
  for (const mode of modes) {
    await page.evaluate((settings) => localStorage.setItem('naadi.settings.v1', JSON.stringify(settings)), { theme: mode.theme, lang: mode.lang });
    await page.reload();
    const before = tileResponses.length;
    await waitForMapTiles(page);
    const tiles = tileResponses.length - before;
    expect(tiles).toBeGreaterThan(0);
    expect(browserErrors, browserErrors.join('\\n')).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`journey-${testInfo.project.name}-${mode.name}.png`) });
    await page.goto(`/speeds?day=weekday&hour=8`);
    await waitForMapTiles(page);
    await expect(page.getByTestId('speeds-play')).toBeVisible();
    await expect(page.getByText(/road cells/)).toBeVisible();
    expect(browserErrors, browserErrors.join('\\n')).toEqual([]);
    await page.getByTestId('speeds-play').click();
    await page.waitForTimeout(1500);
    await page.screenshot({ path: testInfo.outputPath(`speeds-${testInfo.project.name}-${mode.name}.png`) });
    await appendFile('screenshots/index.md', `| ${testInfo.project.name} | ${mode.name} | tiles=${tiles} |\\n`);
  }
  await mkdir('screenshots', { recursive: true });
});
