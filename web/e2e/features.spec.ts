import { test, expect } from '@playwright/test';
import { mockApiData } from './support/mockData';

// Each screen shows its heading once its data has loaded (fixture API in support/mockData.ts). /journey/<id> was a
// placeholder and now opens the planner.
const screens: Array<[string, string]> = [['/','Plan a bus journey'], ['/live','Live buses'], ['/speeds','Road speeds'], ['/accuracy','How accurate is Naadi?'], ['/about','About'], ['/help','Help'], ['/settings','Settings'], ['/stop/10046','Gandhi Darshan'], ['/route/1468','Route 405 towards Mehrauli'], ['/journey/example','Plan a bus journey']];
test.describe('screen contracts', () => {
  test.beforeEach(async ({ page }) => { await mockApiData(page); });
  // The boot splash covers the whole window, so a page only counts as loaded once the splash is gone.
  for (const [path, heading] of screens) test(`loads ${path}`, async ({ page }) => { await page.goto(path); await expect(page.locator('#splash')).toHaveCount(0); await expect(page.locator('h1')).toContainText(heading); });
});

const planned = [
  ['AC-1', 'build and bundle budgets'], ['AC-2', 'unit contracts'], ['AC-5', 'control inventory'], ['AC-6', 'responsive layout'], ['AC-7', 'axe accessibility'], ['AC-8', 'map rendering'], ['AC-9', 'zoom controls'], ['AC-10', 'journey and live bus identity'], ['AC-11', 'theme overlay persistence'], ['AC-12', 'light default'], ['AC-13', 'loading and failure'], ['AC-14', 'departure picker'], ['AC-15', 'bus and metro result groups'], ['AC-16', 'bus journey detail'], ['AC-17', 'metro journey detail'], ['AC-18', 'live next buses'], ['AC-19', 'saved journeys'], ['AC-20', 'live API journey'], ['AC-21', 'secondary screen data'], ['AC-22', 'screenshots'], ['AC-23', 'privacy output scan'], ['AC-24', 'AWS documentation'], ['AC-25', 'release build'],
] as const;
for (const [id, title] of planned) test.fixme(`${id}: ${title}`, async ({ page }) => { await page.goto('/'); expect(await page.locator('[data-testid]').count()).toBeGreaterThan(0); });
