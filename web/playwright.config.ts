import { defineConfig, devices } from '@playwright/test';

const chrome = { channel: 'chrome' as const, launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] } };
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: 1,
  workers: 2,
  reporter: [['list'], ['json', { outputFile: 'test-results/e2e.json' }]],
  webServer: { command: 'npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort', port: 4173, reuseExistingServer: !process.env.CI, env: { NAADI_API_TARGET: process.env.NAADI_API_TARGET ?? 'http://127.0.0.1:8000' } },
  use: { baseURL: 'http://127.0.0.1:4173', ...chrome, trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, ...chrome } },
    { name: 'phone', use: { ...devices['iPhone 13'], viewport: { width: 390, height: 844 }, ...chrome } },
    { name: 'no-webgl', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, ...chrome, launchOptions: { args: [...chrome.launchOptions.args, '--disable-webgl'] } }, testMatch: /fallback\.spec\.ts/ },
  ],
});
