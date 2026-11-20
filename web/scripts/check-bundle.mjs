import { readdir, readFile, stat } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';

const dir = new URL('../dist/assets/', import.meta.url);
const files = (await readdir(dir)).filter((file) => file.endsWith('.js') || file.endsWith('.css'));
const js = files.filter((file) => file.endsWith('.js'));
const css = files.filter((file) => file.endsWith('.css'));
const bytes = async (file) => (await stat(new URL(file, dir))).size;
const gzipped = async (file) => gzipSync(await readFile(new URL(file, dir))).byteLength;
const totalJs = (await Promise.all(js.map(gzipped))).reduce((a, b) => a + b, 0);
const totalCss = (await Promise.all(css.map(gzipped))).reduce((a, b) => a + b, 0);
const main = js.filter((file) => /^index-[\w-]+\.js$/i.test(file));
const mainSize = (await Promise.all(main.map(gzipped))).reduce((a, b) => a + b, 0);
if (mainSize > 350 * 1024) throw new Error(`main JS gzip budget exceeded: ${mainSize}`);
// Road speeds intentionally ships a lazy deck.gl/WebGL stack; keep its total budget separate from the entry budget.
if (totalJs > 1100 * 1024) throw new Error(`JS gzip budget exceeded: ${totalJs}`);
if (totalCss > 50 * 1024) throw new Error(`CSS gzip budget exceeded: ${totalCss}`);
const mainText = (await Promise.all(main.map((file) => readFile(new URL(file, dir), 'utf8')))).join('\n');
if (/deck\.gl|@deck\.gl/i.test(mainText)) throw new Error('deck.gl code found in the main chunk');
console.log(JSON.stringify({ mainGzip: mainSize, jsGzip: totalJs, cssGzip: totalCss, files: files.length }));
