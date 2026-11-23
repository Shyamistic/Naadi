// Screenshots for the README and docs, taken after real interaction with real data.
//
//   npm run build
//   $env:NAADI_API_TARGET='https://13-235-147-97.sslip.io/api'; npx vite preview --host 127.0.0.1 --port 4173 --strictPort
//   node scripts/readme-shots.mjs            # in a second terminal, from web/
//
// BASE (default http://127.0.0.1:4173) picks the site; OUT (default ../docs/images) the folder; FRAMES (default
// ../data/gif_frames) where the Road speeds frames go for scripts/build_docs_figures.py to turn into a GIF.
// ONLY=results,live3d runs a subset. Chrome is driven headless with SwiftShader, so WebGL works without a GPU.
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const BASE = process.env.BASE ?? 'http://127.0.0.1:4173';
const OUT = path.resolve(process.env.OUT ?? '../docs/images/raw');
const FRAMES = path.resolve(process.env.FRAMES ?? '../data/gif_frames/speeds');
const ONLY = process.env.ONLY ? new Set(process.env.ONLY.split(',')) : null;
const EXAMPLE = '/?from=28.665476,77.230173&fromName=GGS+University+ISBT+Kashmere+Gate&to=28.548700,77.256981&toName=Nehru+Place+Terminal&depart=2026-11-24T08:30&modes=bus,metro,rail,shared_auto';
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const desktop = { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 };
const phone = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };

async function open(target, { device = desktop, settings } = {}) {
  const context = await browser.newContext({ ...device, locale: 'en-IN', timezoneId: 'Asia/Kolkata' });
  if (settings) await context.addInitScript((value) => localStorage.setItem('naadi.settings.v1', JSON.stringify(value)), settings);
  const page = await context.newPage();
  page.on('pageerror', (error) => console.warn(`  page error on ${target}: ${error.message}`));
  await page.goto(BASE + target);
  await page.locator('#splash').waitFor({ state: 'detached', timeout: 30_000 }).catch(() => undefined);
  await mapIdle(page);
  return page;
}
// Wait until the map has drawn its tiles (or there is no map on this page).
async function mapIdle(page, extra = 1200) {
  await page.evaluate(() => new Promise((resolve) => {
    const map = window.__naadiMap; if (!map) { resolve(); return; }
    const done = () => resolve(); const timer = setTimeout(done, 20_000);
    if (map.loaded() && map.areTilesLoaded()) { clearTimeout(timer); setTimeout(done, 300); } else map.once('idle', () => { clearTimeout(timer); done(); });
  }));
  await page.waitForTimeout(extra);
}
async function save(page, name, options = {}) { await page.screenshot({ path: path.join(OUT, name), ...options }); console.log(`saved ${name}`); }
async function done(page) { await page.context().close(); }
const want = (name) => !ONLY || ONLY.has(name);

if (want('home')) {
  const page = await open('/');
  await page.getByTestId('city-pulse').waitFor({ timeout: 30_000 });
  await mapIdle(page, 2500);
  await save(page, 'home.png');
  await page.getByTestId('city-pulse').screenshot({ path: path.join(OUT, 'pulse-card.png') }); console.log('saved pulse-card.png');
  await done(page);
}
if (want('results') || want('journey') || want('dial')) {
  const page = await open(EXAMPLE);
  await page.getByTestId('option-card-bus-0').waitFor({ timeout: 30_000 });
  await mapIdle(page, 2000);
  if (want('results')) await save(page, 'results.png');
  await page.getByTestId('option-card-bus-0').click();
  await mapIdle(page, 3500); // the bus is part-way along the route by now
  if (want('journey')) await save(page, 'journey.png');
  if (want('dial')) {
    const section = page.locator('.chakra-section');
    await section.scrollIntoViewIfNeeded();
    // Hover the 06 spoke: the dial runs clockwise from 00 at the top, so 06 is at three o'clock.
    const box = await page.locator('svg.samay-chakra, .samay-chakra svg').first().boundingBox();
    if (box) await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.5, { steps: 4 });
    await page.waitForTimeout(600);
    await section.screenshot({ path: path.join(OUT, 'samay-chakra.png') }); console.log('saved samay-chakra.png');
  }
  await done(page);
}
if (want('live')) {
  const page = await open('/live');
  await page.getByTestId('live-route-link-0').waitFor({ timeout: 30_000 });
  await mapIdle(page, 1500);
  await save(page, 'live.png');
  await done(page);
}
if (want('live3d')) {
  const page = await open('/live');
  await page.getByTestId('live-route-link-0').waitFor({ timeout: 30_000 });
  await page.getByTestId('map-3d').click();
  // ISBT Kashmere Gate, where many buses stand and turn.
  await page.evaluate(() => window.__naadiMap?.jumpTo({ center: [77.2297, 28.6676], zoom: 16.9, pitch: 60, bearing: -28 }));
  await mapIdle(page, 2500);
  await save(page, 'live-3d.png');
  await done(page);
}
if (want('speeds')) {
  const page = await open('/speeds?day=weekday&hour=18');
  await page.getByTestId('speeds-daytype').waitFor({ timeout: 30_000 });
  await mapIdle(page, 3500);
  await save(page, 'speeds.png');
  await done(page);
}
if (want('route')) {
  const page = await open('/route/1468');
  await page.locator('h1').first().waitFor({ timeout: 30_000 });
  await mapIdle(page, 2000);
  await save(page, 'route.png');
  await done(page);
}
if (want('stop')) {
  const page = await open('/stop/817,823');
  await page.getByTestId('departure-row-0').waitFor({ timeout: 30_000 });
  await mapIdle(page, 2000);
  await save(page, 'stop.png');
  await done(page);
}
if (want('accuracy')) {
  const page = await open('/accuracy');
  await page.getByText('At a glance').waitFor({ timeout: 30_000 });
  await page.waitForTimeout(800);
  await save(page, 'accuracy.png');
  await done(page);
}
if (want('hindi')) {
  const page = await open(EXAMPLE, { settings: { lang: 'hi' } });
  await page.getByTestId('option-card-bus-0').waitFor({ timeout: 30_000 });
  await mapIdle(page, 3000);
  await save(page, 'hindi.png');
  await done(page);
}
if (want('dark')) {
  const page = await open(`${EXAMPLE}&option=bus-0`, { settings: { theme: 'dark' } });
  await page.getByTestId('samay-chakra').waitFor({ timeout: 30_000 });
  await mapIdle(page, 3500);
  await save(page, 'dark.png');
  await done(page);
}
if (want('phone')) {
  const home = await open('/', { device: phone });
  await home.getByTestId('sheet-handle').click();
  await mapIdle(home, 1500);
  await save(home, 'phone-home.png');
  await done(home);
  const results = await open(EXAMPLE, { device: phone });
  await results.getByTestId('option-card-bus-0').waitFor({ timeout: 30_000 });
  await results.getByTestId('sheet-handle').click();
  await results.getByTestId('sheet-handle').click();
  await results.waitForTimeout(1200);
  await save(results, 'phone-results.png');
  await done(results);
  const journey = await open(`${EXAMPLE}&option=bus-0`, { device: phone });
  await journey.getByTestId('samay-chakra').waitFor({ timeout: 30_000 });
  await journey.getByTestId('sheet-handle').click();
  await mapIdle(journey, 2500);
  await save(journey, 'phone-journey.png');
  await done(journey);
}
if (want('api')) {
  const page = await open('/api/docs');
  await page.locator('.opblock').first().waitFor({ timeout: 30_000 });
  await page.waitForTimeout(800);
  await save(page, 'api-docs.png');
  await done(page);
}
if (want('frames')) {
  // One frame per hour of an ordinary weekday, for the Road speeds GIF.
  mkdirSync(FRAMES, { recursive: true });
  const page = await open('/speeds?day=weekday&hour=0');
  await page.getByTestId('speeds-daytype').waitFor({ timeout: 30_000 });
  await mapIdle(page, 3500);
  for (let hour = 0; hour < 24; hour += 1) {
    await page.getByTestId('speeds-hour').fill(String(hour));
    await page.waitForTimeout(hour === 0 ? 1500 : 900);
    await page.screenshot({ path: path.join(FRAMES, `hour-${String(hour).padStart(2, '0')}.png`) });
  }
  console.log(`saved 24 frames in ${FRAMES}`);
  await done(page);
}
await browser.close();
