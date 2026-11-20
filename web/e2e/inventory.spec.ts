import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { mockApi } from './support/mockApi';

const selector = 'a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=link],[role=tab],[role=switch],[role=checkbox],[role=radio],[role=slider],[role=combobox],[role=option],[role=menuitem],[data-control]';
test('visible controls have ids and are recorded', async ({ page }, testInfo) => {
  await mockApi(page); await page.goto('/');
  const controls = await page.locator(selector).evaluateAll((nodes) => nodes.filter((node) => { const e = node as HTMLElement; const style = getComputedStyle(e); return style.display !== 'none' && style.visibility !== 'hidden' && !e.closest('[inert],[aria-hidden="true"]'); }).map((node) => ({ tag: node.tagName, testId: node.getAttribute('data-testid'), name: node.getAttribute('aria-label') || node.textContent?.trim() || '' })));
  const missing = controls.filter((control) => !control.testId);
  await mkdir('test-results', { recursive: true }); await writeFile('test-results/inventory.json', JSON.stringify({ state: testInfo.project.name, controls, missing }, null, 2));
  expect(missing, JSON.stringify(missing)).toEqual([]);
});
