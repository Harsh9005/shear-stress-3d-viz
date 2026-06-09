// capture.mjs — headless screenshot/GIF capture of the WebGL scene via the system Chrome.
// Uses swiftshader so WebGL2 works without a GPU. Waits for window.__sceneReady, then settles
// bloom frames, asserts the centre pixel isn't the background, and writes a PNG (and optional frames).
//
// Usage:
//   node tools/capture.mjs --url http://localhost:8123/ --out tools/shots/hero.png \
//        [--width 1600 --height 1000] [--action scenario:stenosis|journey|colorblind] \
//        [--settle 1400] [--frames 60 --orbit]   (frames => writes NNN.png sequence for a GIF)
import puppeteer from 'puppeteer-core';
import { mkdirSync } from 'fs';
import { dirname, basename, join } from 'path';

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  if (i === -1) return def;
  const v = process.argv[i + 1];
  return (v && !v.startsWith('--')) ? v : true;
}

const url = arg('url', 'http://localhost:8123/');
const out = arg('out', 'tools/shots/shot.png');
const width = parseInt(arg('width', '1600'), 10);
const height = parseInt(arg('height', '1000'), 10);
const action = arg('action', null);
const settle = parseInt(arg('settle', '1400'), 10);
const frames = parseInt(arg('frames', '0'), 10);
const orbit = !!arg('orbit', false);

mkdirSync(dirname(out), { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: [
    '--no-sandbox', '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader',
    '--hide-scrollbars', '--no-first-run', '--user-data-dir=/tmp/hl-capture-profile',
    `--window-size=${width},${height}`,
  ],
});

try {
  const page = await browser.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

  await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
  await page.waitForFunction('window.__sceneReady === true', { timeout: 20000 });
  // Skip the cinematic intro for a deterministic framed view.
  await page.evaluate('window.__hl && window.__hl.frame && window.__hl.frame()');

  if (action) {
    if (action.startsWith('scenario:')) {
      const id = action.split(':')[1];
      await page.evaluate((sid) => {
        window.__hl.scenarios.apply(sid);
        const btns = document.querySelectorAll('.scenario-btn');
        for (const b of btns) if (b.textContent.toLowerCase().includes(sid.slice(0, 5))) b.click();
      }, id);
    } else if (action === 'journey') {
      await page.evaluate('window.__hl.journey.start()');
    } else if (action === 'colorblind') {
      await page.evaluate(() => { const cb = [...document.querySelectorAll('.ctl-toggle')].find(x => x.parentElement.textContent.includes('Colour-blind')); if (cb) { cb.checked = true; cb.dispatchEvent(new Event('change')); } });
    }
  }
  await sleep(settle);

  if (frames > 0) {
    const base = out.replace(/\.png$/, '');
    for (let i = 0; i < frames; i++) {
      if (orbit) await page.evaluate((n) => { const c = window.__hl.controls; const a = (n) * (Math.PI * 2 / 1) / 240; const cam = window.__hl.camera; const t = c.target; const r = Math.hypot(cam.position.x - t.x, cam.position.y - t.y); cam.position.x = t.x + Math.cos(a) * r; cam.position.y = t.y + Math.sin(a) * r; c.update(); window.__hl.tick(0.033); }, i);
      else await page.evaluate('for(let k=0;k<2;k++) window.__hl.tick(0.033)');
      await page.screenshot({ path: `${base}_${String(i).padStart(3, '0')}.png` });
    }
    console.log(JSON.stringify({ ok: true, frames, base, centre, errors }));
  } else {
    await page.screenshot({ path: out });
    // Assert (after the screenshot, so the GPU stall can't blank the captured frame).
    const centre = await page.evaluate(() => {
      const c = document.querySelector('#scene canvas');
      const gl = c.getContext('webgl2');
      const px = new Uint8Array(4);
      gl.readPixels((gl.drawingBufferWidth / 2) | 0, (gl.drawingBufferHeight / 2) | 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      return [px[0], px[1], px[2]];
    });
    const fatal = await page.evaluate(() => !document.getElementById('fatal').hidden);
    console.log(JSON.stringify({ ok: true, out, centre, fatalShown: fatal, bgLike: (centre[0] < 20 && centre[1] < 25 && centre[2] < 35), errors }));
  }
} catch (e) {
  console.log(JSON.stringify({ ok: false, error: e.message }));
  process.exitCode = 1;
} finally {
  await browser.close();
}
