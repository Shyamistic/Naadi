import { test, expect } from '@playwright/test';
import { mockApi } from './support/mockApi';

test.describe('WP1 shell', () => {
  test.beforeEach(async ({ page }) => { await mockApi(page); });
  test('loads the planner with civic shell and map', async ({ page }) => {
    await page.goto('/');
    await page.locator('#splash').waitFor({ state: 'hidden' });
    await expect(page.locator('[data-testid="place-from-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="map"]')).toBeVisible();
  });
  test('settings persists theme and language', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    await page.getByTestId('settings-theme-dark').evaluate((button) => (button as HTMLButtonElement).click());
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('naadi.settings.v1') ?? '{}').theme)).toBe('dark');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.getByTestId('settings-lang-hi').evaluate((button) => (button as HTMLButtonElement).click());
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('naadi.settings.v1') ?? '{}').lang)).toBe('hi');
  });
});
