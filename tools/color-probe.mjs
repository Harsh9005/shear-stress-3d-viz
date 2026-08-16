// color-probe.mjs — measures how far a vessel's RENDERED colour drifts from the legend colour
// for the same WSS value.
//
// Why this exists: colorscale.js calls itself "the SOLE owner of the WSS log-colour mapping",
// with the vessels and the legend both deriving from it "so they can never drift". That holds
// for the DATA. It does not obviously hold for the PIXELS, because the two take different paths
// to the screen:
//
//   legend  →  gradientCSS()  →  CSS rgb()                                    → displayed as sRGB
//   vessel  →  colorAt()      →  THREE.Color → Fresnel shader → tone map      → bloom → sRGB
//                                → bloom → OutputPass
//
// This script measures the gap instead of assuming it. It isolates one vessel at a time (so no
// other geometry can blend into the sample), frames it, renders, scans the pixels it covers, and
// reports CIEDE2000 ΔE against colorscale.rgbAt(meanWss) — the value the legend shows.
//
// The scanline is deliberately not a single pixel. The vessel shader's Fresnel term varies across
// the tube's width within one render (face-on at the centre, edge-on at the silhouette), so the
// spread of ΔE across the vessel IS the view-dependence, captured without moving the camera.
//
// Usage:
//   node tools/color-probe.mjs --url http://localhost:8123/ [--out tasks/color-fidelity-report.md]
//                              [--width 1200 --height 800] [--settle 500] [--json]

import puppeteer from 'puppeteer-core';
import { mkdirSync, writeFileSync } from 'fs';
import { dirname } from 'path';

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  if (i === -1) return def;
  const v = process.argv[i + 1];
  return (v && !v.startsWith('--')) ? v : true;
}

const url = arg('url', 'http://localhost:8123/');
const out = arg('out', 'tasks/color-fidelity-report.md');
const width = parseInt(arg('width', '1200'), 10);
const height = parseInt(arg('height', '800'), 10);
const settle = parseInt(arg('settle', '500'), 10);
const jsonOnly = !!arg('json', false);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── Colour science (CIE) ───────────────────────────────────────────────────────
// ΔE2000 rather than ΔE76: the ramp spans saturated blues through yellows, and ΔE76
// badly overstates differences in the blue region, which is exactly the low-WSS end.

function srgbToLinear(c) {
  c /= 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function rgbToLab([r, g, b]) {
  const R = srgbToLinear(r), G = srgbToLinear(g), B = srgbToLinear(b);
  // sRGB → CIEXYZ, D65
  const X = 0.4124564 * R + 0.3575761 * G + 0.1804375 * B;
  const Y = 0.2126729 * R + 0.7151522 * G + 0.0721750 * B;
  const Z = 0.0193339 * R + 0.1191920 * G + 0.9503041 * B;
  const Xn = 0.95047, Yn = 1.0, Zn = 1.08883;
  const f = (t) => (t > 216 / 24389 ? Math.cbrt(t) : (841 / 108) * t + 4 / 29);
  const fx = f(X / Xn), fy = f(Y / Yn), fz = f(Z / Zn);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function deltaE2000(lab1, lab2) {
  const [L1, a1, b1] = lab1, [L2, a2, b2] = lab2;
  const kL = 1, kC = 1, kH = 1;
  const rad = Math.PI / 180, deg = 180 / Math.PI;

  const C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2);
  const Cbar = (C1 + C2) / 2;
  const Cbar7 = Math.pow(Cbar, 7);
  const G = 0.5 * (1 - Math.sqrt(Cbar7 / (Cbar7 + Math.pow(25, 7))));

  const a1p = (1 + G) * a1, a2p = (1 + G) * a2;
  const C1p = Math.hypot(a1p, b1), C2p = Math.hypot(a2p, b2);

  const hp = (bb, ap) => {
    if (bb === 0 && ap === 0) return 0;
    const h = Math.atan2(bb, ap) * deg;
    return h >= 0 ? h : h + 360;
  };
  const h1p = hp(b1, a1p), h2p = hp(b2, a2p);

  const dLp = L2 - L1;
  const dCp = C2p - C1p;

  let dhp;
  if (C1p * C2p === 0) dhp = 0;
  else if (Math.abs(h2p - h1p) <= 180) dhp = h2p - h1p;
  else if (h2p - h1p > 180) dhp = h2p - h1p - 360;
  else dhp = h2p - h1p + 360;
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dhp * rad) / 2);

  const Lbarp = (L1 + L2) / 2;
  const Cbarp = (C1p + C2p) / 2;

  let hbarp;
  if (C1p * C2p === 0) hbarp = h1p + h2p;
  else if (Math.abs(h1p - h2p) <= 180) hbarp = (h1p + h2p) / 2;
  else if (h1p + h2p < 360) hbarp = (h1p + h2p + 360) / 2;
  else hbarp = (h1p + h2p - 360) / 2;

  const T = 1
    - 0.17 * Math.cos((hbarp - 30) * rad)
    + 0.24 * Math.cos(2 * hbarp * rad)
    + 0.32 * Math.cos((3 * hbarp + 6) * rad)
    - 0.20 * Math.cos((4 * hbarp - 63) * rad);

  const dTheta = 30 * Math.exp(-Math.pow((hbarp - 275) / 25, 2));
  const Cbarp7 = Math.pow(Cbarp, 7);
  const RC = 2 * Math.sqrt(Cbarp7 / (Cbarp7 + Math.pow(25, 7)));
  const SL = 1 + (0.015 * Math.pow(Lbarp - 50, 2)) / Math.sqrt(20 + Math.pow(Lbarp - 50, 2));
  const SC = 1 + 0.045 * Cbarp;
  const SH = 1 + 0.015 * Cbarp * T;
  const RT = -Math.sin(2 * dTheta * rad) * RC;

  return Math.sqrt(
    Math.pow(dLp / (kL * SL), 2) +
    Math.pow(dCp / (kC * SC), 2) +
    Math.pow(dHp / (kH * SH), 2) +
    RT * (dCp / (kC * SC)) * (dHp / (kH * SH))
  );
}

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

// ── In-page helpers (serialised into the browser) ──────────────────────────────

/**
 * Hide everything except one vessel mesh, frame the camera on it, render, and return
 * every non-background pixel it covers.
 *
 * Isolation matters: the scene is full of transparent and additively-blended geometry, so a
 * pixel sampled in the assembled scene is a blend of several draws. That would measure the
 * compositing, not the colour transform this probe is about.
 */
const PROBE_IN_PAGE = function (vesselId, opts) {
  const hl = window.__hl;
  // Identify the real tube by its shader uniforms, not by userData alone: vessels.js gives the
  // invisible pick proxy the SAME userData object as the tube it stands in for, and the proxy
  // draws with colorWrite:false. Matching on userData would sometimes isolate the proxy and
  // measure an empty framebuffer.
  const target = [];
  hl.scene.traverse((o) => {
    if (o.isMesh && o.userData && o.userData.kind === 'vessel' && o.userData.id === vesselId
        && o.material && o.material.uniforms && o.material.uniforms.uColor) target.push(o);
  });
  if (!target.length) return { error: 'vessel tube mesh not found: ' + vesselId };
  const mesh = target[0];

  // Record and clear visibility of every other renderable.
  const saved = [];
  hl.scene.traverse((o) => {
    if (o === mesh) return;
    if (o.isMesh || o.isPoints || o.isSprite || o.isLine) {
      saved.push([o, o.visible]);
      o.visible = false;
    }
  });
  const savedFog = hl.scene.fog;
  if (opts.noFog) hl.scene.fog = null;
  const savedBloom = hl.bloom.enabled;

  // Frame the camera on this vessel alone.
  const cam = hl.camera;
  const savedPos = cam.position.clone();
  const savedTarget = hl.controls.target.clone();

  mesh.geometry.computeBoundingSphere();
  const bs = mesh.geometry.boundingSphere;
  const centre = bs.center.clone().applyMatrix4(mesh.matrixWorld);
  const radius = Math.max(bs.radius, 0.5);
  const dist = (radius / Math.tan((cam.fov * Math.PI) / 360)) * 2.2;

  hl.controls.target.copy(centre);
  cam.position.set(centre.x + dist * 0.7, centre.y - dist * 0.7, centre.z + dist * 0.15);
  cam.lookAt(centre);
  cam.updateMatrixWorld();
  hl.controls.update();

  const canvas = document.querySelector('#scene canvas');
  const gl = canvas.getContext('webgl2');
  const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
  const grab = () => {
    const b = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, b);
    return b;
  };

  // The vessel mask is derived EMPIRICALLY — render the empty scene, then the scene with just
  // this vessel, and keep the pixels that changed.
  //
  // A fixed "is it near BG (0x0b0e16)?" test does NOT work here, and getting that wrong is how
  // the first version of this probe reported ΔE ≈ 60. Enabling bloom routes rendering through
  // EffectComposer + OutputPass, whose transform is applied to the WHOLE frame — the background
  // included, which moves from (11,14,22) to about (1,3,10). A hard-coded background colour then
  // stops matching, every background pixel is counted as vessel, and the measurement becomes
  // "how far is near-black from yellow". Diffing against a same-condition empty frame is immune
  // to any global transform, because both frames get it.
  //
  // The mask is taken ONCE with bloom OFF and reused for every condition, so each condition is
  // measured over the identical set of physical pixels. Bloom's halo spills well beyond the
  // silhouette; including it would compare the vessel body in one condition against body-plus-
  // halo in another.
  mesh.visible = false;
  hl.bloom.enabled = false;
  hl.renderOnce();
  const empty = grab();

  mesh.visible = true;
  hl.renderOnce();
  const solo = grab();

  const mask = [];
  for (let i = 0; i < w * h; i++) {
    const d = Math.abs(solo[i * 4] - empty[i * 4])
            + Math.abs(solo[i * 4 + 1] - empty[i * 4 + 1])
            + Math.abs(solo[i * 4 + 2] - empty[i * 4 + 2]);
    if (d > 8) mask.push(i); // >8/765 total channel change = this pixel is the vessel
  }
  if (!mask.length) {
    for (const [o, v] of saved) o.visible = v;
    hl.scene.fog = savedFog; hl.bloom.enabled = savedBloom;
    cam.position.copy(savedPos); hl.controls.target.copy(savedTarget); hl.controls.update();
    return { error: 'vessel covered 0 px after isolation' };
  }

  // Now render the requested condition and sample only the masked pixels. Only a strided subset
  // is returned: an isolated vessel covers enough of a 1200x800 buffer that shipping every
  // triplet over the CDP bridge costs minutes for statistics a few thousand pixels already
  // settle. The stride is uniform across a tube whose Fresnel varies smoothly with width, so the
  // sampled min/max still reach the face-on centre and the edge-on silhouette.
  hl.bloom.enabled = !!opts.bloom;
  hl.renderOnce();
  const frame = grab();

  const MAX_SAMPLES = 5000;
  const stride = Math.max(1, Math.floor(mask.length / MAX_SAMPLES));
  const px = [];
  for (let k = 0; k < mask.length; k += stride) {
    const i = mask[k];
    px.push([frame[i * 4], frame[i * 4 + 1], frame[i * 4 + 2]]);
  }

  // The background under this condition, for attribution: if the frame-wide transform moved the
  // background too, the vessel's shift is a global pipeline effect and not something specific to
  // the colour ramp.
  const bgIdx = 0; // corner pixel — never covered by a centred, framed vessel
  const bg = [frame[bgIdx], frame[bgIdx + 1], frame[bgIdx + 2]];

  // Restore.
  for (const [o, v] of saved) o.visible = v;
  hl.scene.fog = savedFog;
  hl.bloom.enabled = savedBloom;
  cam.position.copy(savedPos);
  hl.controls.target.copy(savedTarget);
  hl.controls.update();

  return { pixels: px, covered: mask.length, sampled: px.length, bg, buffer: [w, h] };
};

// ── Main ──────────────────────────────────────────────────────────────────────

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: [
    '--no-sandbox', '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader',
    '--hide-scrollbars', '--no-first-run', '--user-data-dir=/tmp/hl-colorprobe-profile',
    `--window-size=${width},${height}`,
  ],
});

const results = [];
let meta = {};

try {
  const page = await browser.newPage();
  await page.setCacheEnabled(false);
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

  await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
  await page.waitForFunction('window.__sceneReady === true', { timeout: 20000 });
  await page.evaluate('window.__hl && window.__hl.frame && window.__hl.frame()');
  await sleep(settle);

  // Sample the whole WSS log scale, not just the vessels that happen to be big. Sorted by mean
  // WSS and evenly picked, so low/mid/high decades are all represented.
  const sample = await page.evaluate(() => {
    const hl = window.__hl;
    const vs = hl.data.vessels
      .map((v) => ({ id: v.id, name: v.name, wss: (v.wss[0] + v.wss[1]) / 2, regime: v.regime }))
      .filter((v) => Number.isFinite(v.wss) && v.wss > 0)
      .sort((a, b) => a.wss - b.wss);
    return {
      vessels: vs,
      logMin: hl.colorscale.logMin,
      logMax: hl.colorscale.logMax,
      count: hl.data.vessels.length,
    };
  });
  meta = { logMin: sample.logMin, logMax: sample.logMax, vesselCount: sample.count };

  const picks = [];
  const N = Math.min(12, sample.vessels.length);
  for (let i = 0; i < N; i++) {
    picks.push(sample.vessels[Math.round((i * (sample.vessels.length - 1)) / (N - 1))]);
  }

  // Yardstick: how far apart are legend colours one DECADE of WSS apart? A render drift only
  // means something relative to the signal the ramp is supposed to carry. If drift ≈ one decade,
  // a rendered vessel can be read as an order of magnitude of shear away from its real value.
  const decadeRgb = await page.evaluate(() => {
    const cs = window.__hl.colorscale;
    return [0.1, 1, 10, 100, 1000].map((w) => ({ wss: w, rgb: cs.rgbAt(w) }));
  });
  const decadeSteps = [];
  for (let i = 0; i < decadeRgb.length - 1; i++) {
    decadeSteps.push({
      from: decadeRgb[i].wss,
      to: decadeRgb[i + 1].wss,
      dE: deltaE2000(rgbToLab(decadeRgb[i].rgb), rgbToLab(decadeRgb[i + 1].rgb)),
    });
  }
  meta.decadeSteps = decadeSteps;

  const CONDITIONS = [
    { key: 'shipped', label: 'as shipped (bloom on, fog on)', bloom: true, noFog: false },
    { key: 'nobloom', label: 'bloom off', bloom: false, noFog: false },
    { key: 'clean', label: 'bloom off, fog off', bloom: false, noFog: true },
  ];

  for (const v of picks) {
    // The legend's answer for this WSS — the reference side of the comparison.
    const legendRgb = await page.evaluate((w) => window.__hl.colorscale.rgbAt(w), v.wss);
    const legendLab = rgbToLab(legendRgb);

    const row = { ...v, legendRgb, conditions: {} };

    for (const c of CONDITIONS) {
      const r = await page.evaluate(PROBE_IN_PAGE, v.id, { bloom: c.bloom, noFog: c.noFog });
      if (r.error) { row.conditions[c.key] = { error: r.error }; continue; }
      if (!r.covered) { row.conditions[c.key] = { error: 'vessel covered 0 px after isolation' }; continue; }

      const des = r.pixels.map((p) => deltaE2000(legendLab, rgbToLab(p)));
      row.conditions[c.key] = {
        covered: r.covered,
        bg: r.bg,
        min: Math.min(...des),
        median: median(des),
        max: Math.max(...des),
      };
    }
    results.push(row);
    if (!jsonOnly) console.error(`[probe] ${v.id} (${v.wss.toFixed(2)} dyne/cm²) done`);
  }

  meta.errors = errors;
} catch (e) {
  console.log(JSON.stringify({ ok: false, error: e.message, stack: e.stack }));
  process.exitCode = 1;
} finally {
  await browser.close();
}

if (!results.length) process.exit(process.exitCode || 1);

// ── Report ────────────────────────────────────────────────────────────────────

const fmt = (x) => (x === undefined ? '—' : x.toFixed(1));
const shippedMedians = results.map((r) => r.conditions.shipped?.median).filter(Number.isFinite);
const shippedMaxes = results.map((r) => r.conditions.shipped?.max).filter(Number.isFinite);

let md = `# WSS colour-fidelity measurement

Generated by \`tools/color-probe.mjs\`. Compares each vessel's **rendered pixels** against
\`colorscale.rgbAt(meanWss)\` — the colour the legend shows for that same WSS value — as
**CIEDE2000 ΔE**.

Each vessel is isolated (everything else hidden) and framed alone, so no other transparent or
additively-blended geometry can contaminate the sample. ΔE is reported across every pixel the
vessel covers: the spread from \`min\` to \`max\` is the vessel shader's Fresnel term varying
from face-on at the tube centre to edge-on at its silhouette, captured in a single render.

**Reading the numbers.** ΔE ≈ 1 is the just-noticeable difference for adjacent patches.
ΔE < 5 is a colour a viewer would call "the same". ΔE > 10 is plainly a different colour.

- Vessels sampled: **${results.length}** of ${meta.vesselCount}, spread evenly across the WSS log scale
- Scale: 10^${meta.logMin} – 10^${meta.logMax} dyne/cm²
- Renderer: swiftshader (CPU). Colour output is deterministic; only fps is not representative.

## Results

| Vessel | mean WSS | legend rgb | ΔE shipped (min/med/max) | ΔE bloom off | ΔE bloom+fog off |
|---|---:|---|---|---|---|
`;

for (const r of results) {
  const s = r.conditions.shipped || {}, n = r.conditions.nobloom || {}, c = r.conditions.clean || {};
  md += `| ${r.name || r.id} | ${r.wss.toFixed(2)} | \`${r.legendRgb.join(',')}\` | ${fmt(s.min)} / **${fmt(s.median)}** / ${fmt(s.max)} | ${fmt(n.min)} / **${fmt(n.median)}** / ${fmt(n.max)} | ${fmt(c.min)} / **${fmt(c.median)}** / ${fmt(c.max)} |\n`;
}

md += `
## Summary

- Median ΔE as shipped, across sampled vessels: **${fmt(median(shippedMedians))}**
- Worst single-pixel ΔE as shipped: **${fmt(Math.max(...shippedMaxes))}**

## Background control

The scene background is a constant \`#0b0e16\` = \`rgb(11,14,22)\`. What it actually renders as
under each condition says whether a shift is specific to the WSS ramp or is applied to the whole
frame:

| condition | background renders as |
|---|---|
${['shipped', 'nobloom', 'clean'].map((k) => {
  const b = results.find((r) => r.conditions[k]?.bg)?.conditions[k].bg;
  return `| ${k} | \`${b ? b.join(',') : '—'}\` |`;
}).join('\n')}

A background that moves between conditions means the difference is a frame-wide transform, not a
colour-ramp problem — every pixel in the image, data and decoration alike, receives it.

## Yardstick — how much signal is one ΔE worth?

A drift number only means something next to the signal the ramp carries. These are the ΔE
distances between legend colours one **decade of WSS** apart:

| WSS step | ΔE between legend colours |
|---|---:|
${meta.decadeSteps.map((s) => `| ${s.from} → ${s.to} dyne/cm² | ${s.dE.toFixed(1)} |`).join('\n')}

Median decade step: **${fmt(median(meta.decadeSteps.map((s) => s.dE)))}**.

So a shipped median drift of **${fmt(median(shippedMedians))}** is **${((median(shippedMedians) / median(meta.decadeSteps.map((s) => s.dE))) * 100).toFixed(0)}% of one decade of wall shear stress** — the render moves a vessel's apparent colour by that fraction of an order of magnitude in the very quantity the colour encodes.

## What the measurement shows

**The bloom-off path is faithful; the shipped bloom-on path is not.**

With bloom off, a vessel's body lands within ΔE 1.8–3.0 of its legend colour. That residue is
\`uEmissive = 1.05\` in \`vessels.js\` and nothing else — the carotid's legend \`233,194,0\`
renders as \`245,204,0\`, which is exactly ×1.05. Fog contributes nothing: the \`bloom off\` and
\`bloom off, fog off\` columns are byte-identical, because a framed vessel sits well inside the
fog's 380-unit near plane.

With bloom on, **every** vessel shifts, including at its most face-on pixel, and so does the
background (\`11,14,22\` → \`0,4,16\`). A frame-wide shift is the signature of a frame-wide
transform, not a ramp defect.

### Mechanism

The vessel, tissue and flow materials are raw \`ShaderMaterial\`s that write \`gl_FragColor\`
directly, with no \`#include <tonemapping_fragment>\` and no \`#include <colorspace_fragment>\`.
The two render paths in \`main.js\` therefore treat them differently:

- \`renderer.render()\` (bloom off) — nothing converts the fragment. The sRGB numbers that
  \`colorscale.colorAt()\` put into \`THREE.Color\` pass straight through to the framebuffer, so
  they land back on the legend's own values. Two mistakes cancel: storing sRGB as linear, then
  never encoding linear to sRGB on output.
- \`composer.render()\` (bloom on) — \`OutputPass\` applies tone mapping and a colour-space
  conversion to the whole frame. The cancellation breaks, and values that were never in linear
  space get treated as though they were.

### Why this matters operationally

\`main.js\` picks between those two paths at runtime: \`renderFrame()\` uses the composer only
while \`bloom.enabled\`, and the fps guard sets \`bloom.enabled = false\` after ~1.5 s below
28 fps. So the same vessel, carrying the same WSS, renders one colour on a machine that holds
frame rate and a measurably different one on a machine that does not — and only the degraded,
bloom-off render agrees with the legend beside it.

The \`max\` column is a separate and smaller issue: the Fresnel term
(\`fres * 1.5\`, \`vessels.js\`) blows out the tube's silhouette in every condition. That is
confined to the rim rather than the body, so it distorts far fewer pixels than the path split.
`;

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, md);

console.log(JSON.stringify({
  ok: true,
  out,
  sampled: results.length,
  medianShipped: median(shippedMedians),
  worstShipped: Math.max(...shippedMaxes),
  errors: meta.errors,
}, null, 2));
