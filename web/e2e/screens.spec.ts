import { test } from '@playwright/test';
import { mkdir, appendFile } from 'node:fs/promises';

test('capture the WP1 shell', async ({ page }, testInfo) => {
  await page.goto('/'); await page.screenshot({ path: testInfo.outputPath('plan-empty.png'), fullPage: true });
  await mkdir('screenshots', { recursive: true });
  await appendFile('screenshots/index.md', `| ${testInfo.project.name} | plan-empty | ${testInfo.outputDir} |\n`);
});
