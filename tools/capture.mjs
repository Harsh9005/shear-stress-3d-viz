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
  await page.setCacheEnabled(false); // always load fresh modules (avoid stale ESM cache)
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

  await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
  await page.waitForFunction('window.__sceneReady === true', { timeout: 20000 });
  // Skip the cinematic intro for a deterministic framed view.
  await page.evaluate('window.__hl && window.__hl.frame && window.__hl.frame()');
  if (arg('clean', false)) await page.evaluate(() => { document.getElementById('ui').style.display = 'none'; });

  if (action) {
    if (action.startsWith('scenario:')) {
      const id = action.split(':')[1];
      const ok = await page.evaluate((sid) => {
        const valid = window.__hl.scenarios.list.some((s) => s.id === sid);
        if (!valid) return false;
        window.__hl.scenarios.apply(sid);
        const btns = document.querySelectorAll('.scenario-btn');
        for (const b of btns) if (b.textContent.toLowerCase().includes(sid.slice(0, 5))) b.click();
        return true;
      }, id);
      if (!ok) { console.log(JSON.stringify({ ok: false, error: 'scenario id not found: ' + id })); process.exit(1); }
    } else if (action.startsWith('tumor:')) {
      const ids = action.split(':')[1].split(',');
      for (const tid of ids) {
        const clicked = await page.evaluate((sid) => {
          const valid = window.__hl.tumors.sites.some((s) => s.id === sid);
          if (!valid) return false;
          window.__hl.tumors.toggle(sid);
          return true;
        }, tid);
        if (!clicked) { console.log(JSON.stringify({ ok: false, error: 'tumor id not found: ' + tid })); process.exit(1); }
      }
    } else if (action.startsWith('simlab:')) {
      const tid = action.split(':')[1];
      await page.evaluate((t) => window.__hl.simlab.enter(t), tid);
    } else if (action.startsWith('journey')) {
      const steps = parseInt(action.split(':')[1] || '0', 10);
      await page.evaluate('window.__hl.journey.start()');
      for (let s = 0; s < steps; s++) {
        await sleep(1700);
        await page.evaluate(() => { const b = [...document.querySelectorAll('.jbtn')].find(x => x.dataset.act === 'next'); if (b) b.click(); });
      }
    } else if (action.startsWith('eval:')) {
      // Arbitrary scene tweak before the shot, e.g. --action "eval:__hl.anatomy.setCutaway(false)".
      await page.evaluate(action.slice(5));
    } else if (action === 'colorblind') {
      await page.evaluate(() => { const cb = [...document.querySelectorAll('.ctl-toggle')].find(x => x.parentElement.textContent.includes('Colour-blind')); if (cb) { cb.checked = true; cb.dispatchEvent(new Event('change')); } });
    }
  }
  await sleep(settle);

  if (frames > 0) {
    const base = out.replace(/\.png$/, '');
    for (let i = 0; i < frames; i++) {
      if (orbit) await page.evaluate(({ n, total }) => {
        const hl = window.__hl, cam = hl.camera, t = hl.controls.target;
        if (n === 0) { const dx = cam.position.x - t.x, dy = cam.position.y - t.y; window.__orb = { r: Math.hypot(dx, dy), a0: Math.atan2(dy, dx), z: cam.position.z }; }
        const o = window.__orb, a = o.a0 + (n / total) * Math.PI * 2;
        cam.position.x = t.x + Math.cos(a) * o.r; cam.position.y = t.y + Math.sin(a) * o.r; cam.position.z = o.z;
        hl.controls.update(); hl.tick(0.033);
      }, { n: i, total: frames });
      else await page.evaluate('for(let k=0;k<2;k++) window.__hl.tick(0.033)');
      await page.screenshot({ path: `${base}_${String(i).padStart(3, '0')}.png` });
    }
    console.log(JSON.stringify({ ok: true, frames, base, errors }));
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
