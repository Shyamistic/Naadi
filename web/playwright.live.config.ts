import base from './playwright.config';
import { defineConfig } from '@playwright/test';

// Tests tagged @live, on real data. By default the local build runs in `vite preview` with /api proxied to the live
// API. Set NAADI_BASE_URL (e.g. https://13-235-147-97.sslip.io) to test a deployed site as it is.
const deployed = process.env.NAADI_BASE_URL;
// defineConfig skips undefined values when merging, so the base webServer is dropped here, not in the override.
export default defineConfig({ ...base, webServer: undefined }, {
  use: { ...base.use, baseURL: deployed ?? 'http://127.0.0.1:4173' },
  webServer: deployed ? undefined : { command: 'npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort', port: 4173, reuseExistingServer: !process.env.CI, env: { NAADI_API_TARGET: 'https://13-235-147-97.sslip.io/api' } },
  grep: /@live/,
  workers: 1,
});
