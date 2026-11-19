import { test, expect } from '@playwright/test';
import { mockApi } from './support/mockApi';

test.describe('WP1 shell', () => {
  test.beforeEach(async ({ page }) => { await mockApi(page); });
  test('loads the planner with civic shell and map', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('[data-testid="header-home"]')).toBeVisible();
    await expect(page.locator('[data-testid="place-from-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="map"]')).toBeVisible();
  });
  test('settings persists theme and language', async ({ page }) => {
    await page.goto('/settings');
    await page.getByTestId('settings-theme-dark').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.getByTestId('settings-lang-hi').click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'hi');
  });
});
