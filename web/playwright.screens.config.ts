import base from './playwright.config';
import { defineConfig } from '@playwright/test';
export default defineConfig(base, { outputDir: 'screenshots/test-results', snapshotDir: 'screenshots', use: { ...base.use, deviceScaleFactor: 2 }, webServer: { ...base.webServer, env: { NAADI_API_TARGET: 'http://127.0.0.1:8077' } }, testMatch: /screens\.spec\.ts/ });
