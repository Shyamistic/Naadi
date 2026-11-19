import base from './playwright.config';
import { defineConfig } from '@playwright/test';
export default defineConfig(base, { use: { ...base.use, baseURL: 'http://127.0.0.1:4173' }, webServer: { ...base.webServer, env: { NAADI_API_TARGET: 'https://13-235-147-97.sslip.io/api' } }, grep: /@live/ });
