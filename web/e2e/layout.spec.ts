import { test, expect } from '@playwright/test';
import { mockApi } from './support/mockApi';

test('shell has no horizontal overflow', async ({ page }) => {
  await mockApi(page); await page.goto('/');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  const badges = page.locator('[data-route-badge]');
  for (let i = 0; i < await badges.count(); i++) expect(await badges.nth(i).evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBeTruthy();
});
