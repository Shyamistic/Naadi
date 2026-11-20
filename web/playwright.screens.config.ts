import base from './playwright.config';
import { defineConfig } from '@playwright/test';

export default defineConfig(base, {
  outputDir: 'screenshots/test-results',
  snapshotDir: 'screenshots',
  use: { ...base.use, deviceScaleFactor: 2 },
  webServer: { command: 'npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort', port: 4173, timeout: 180_000, reuseExistingServer: !process.env.CI, env: { NAADI_API_TARGET: 'http://127.0.0.1:8020' } },
  testMatch: /screens\.spec\.ts/,
});
