// main.js — bootstrap: renderer, scene, post-processing, the RAF loop, and wiring of all modules.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

import { DATA } from '../data/data.js';
import { createColorScale } from './colorscale.js';
import { buildVasculature } from './vessels.js';
import { buildFlow } from './flow.js';
import { buildPanels } from './panels.js';
import { buildUI } from './ui.js';
import { createScenarioController } from './scenarios.js';
import { createJourney } from './journey.js';
import { createTumors } from './tumors.js';
import { createSimLab } from './simlab.js';
import { createAnatomy } from './anatomy.js';

const BG = 0x0b0e16;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const coarsePointer = window.matchMedia('(pointer: coarse)').matches;
const lowMemory = (navigator.deviceMemory || 8) <= 4;

const state = (window.__appState = {
  activeScenarioId: 'healthy',
  integrityPct: 100,
  fps: 0,
  particleCount: 0,
  sceneReady: false,
  colorblind: false,
});

function fail(msg) {
  console.error('[hemodynamic]', msg);
  const l = document.getElementById('loading');
  const f = document.getElementById('fatal');
  const fm = document.getElementById('fatal-msg');
  if (l) l.hidden = true;
  if (f) f.hidden = false;
  if (fm && msg) fm.textContent = msg;
  // Best-effort: render the science fallback (spectrum + shear gap) with no 3D.
  try {
    const host = document.getElementById('fatal-panels');
    if (host) buildPanels(DATA, createColorScale(DATA)).mountFallback(host);
  } catch (e) { /* fallback is best-effort */ }
}

function init() {
  const container = document.getElementById('scene');
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance', preserveDrawingBuffer: true });
  if (!renderer.capabilities.isWebGL2) { fail('WebGL2 is required for this visualization.'); return; }

  let width = container.clientWidth || window.innerWidth;
  let height = container.clientHeight || window.innerHeight;
  const dprCap = coarsePointer ? 1.25 : 1.5;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, dprCap));
  renderer.setSize(width, height);
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 1.05;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(BG);
  // Fog reaches past the whole body (286 units tall); at the old 180-360 it was fading
  // the far half of the figure into the background and muddying the tissue colour.
  scene.fog = new THREE.Fog(BG, 380, 900);

  const camera = new THREE.PerspectiveCamera(42, width / height, 0.5, 2000);
  camera.up.set(0, 0, 1); // anatomical Z is vertical

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.rotateSpeed = 0.8;
  controls.minDistance = 30;
  controls.maxDistance = 480;
  controls.enablePan = !coarsePointer;
  // Don't let one-finger drag scroll-jack the page on touch.
  controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };

  // Lighting rig for the medical-illustration read. anatomy.js lights tissue in its own shader
  // so it looks the same from every angle; these lights shape the vessels.
  scene.add(new THREE.AmbientLight(0x9fb4d0, 0.42));
  const key = new THREE.DirectionalLight(0xffffff, 0.85); key.position.set(60, -90, 120); scene.add(key);
  const fill = new THREE.DirectionalLight(0xa8c0e0, 0.35); fill.position.set(-90, -40, 20); scene.add(fill);
  const rim = new THREE.DirectionalLight(0x5878b8, 0.5); rim.position.set(-40, 90, -60); scene.add(rim);

  const colorscale = createColorScale(DATA);

  // ── Frame the camera. Starts on the vasculature, then re-frames on the whole body once the
  //    anatomy loads — the body is taller than the vessel tree (it has a head and feet), so
  //    framing on vessels alone crops it. Re-framing is skipped the moment the viewer has
  //    touched the controls, so it can never yank a camera out from under them. ──
  const framedPos = new THREE.Vector3();
  function frameOn(box) {
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.z) * 0.62;
    const dist = radius / Math.tan((camera.fov * Math.PI) / 360) * 1.05;
    controls.target.copy(center);
    framedPos.set(center.x + dist * 0.62, center.y - dist * 0.72, center.z + dist * 0.16);
  }
  frameOn(computeBounds(DATA));

  // Post-processing
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  // Low bloom: enough to keep the WSS colours reading as luminous data, not so much that lit
  // tissue washes out. The old value (0.72) belonged to the all-emissive x-ray look.
  const bloom = new UnrealBloomPass(new THREE.Vector2(width, height), 0.34, 0.45, 0.86);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  composer.setPixelRatio(renderer.getPixelRatio());
  composer.setSize(width, height);

  // Shared app context handed to every module.
  const updaters = [];
  let cameraOwner = null;
  const ctx = {
    THREE, scene, camera, renderer, controls, composer, bloom, colorscale, data: DATA,
    container, state, reducedMotion, coarsePointer, lowMemory,
    registerUpdate: (fn) => updaters.push(fn),
    setBloom: (on) => { bloom.enabled = on; },
    // cinematic-mode lock: only one of {journey, simlab} may drive the camera at a time
    takeCamera: (name) => { if (cameraOwner && cameraOwner !== name) return false; cameraOwner = name; return true; },
    releaseCamera: (name) => { if (cameraOwner === name) cameraOwner = null; },
    cameraOwner: () => cameraOwner,
  };

  // ── Build subsystems (each guarded so one failure can't blank the app) ──
  let vessels, flow, panels, scenarios, journey, tumors, simlab, anatomy;
  try { anatomy = createAnatomy(ctx, DATA); } catch (e) { console.error('anatomy', e); }
  try { vessels = buildVasculature(ctx, DATA); } catch (e) { console.error('vessels', e); }
  try { flow = buildFlow(ctx, DATA); } catch (e) { console.error('flow', e); }
  try { panels = buildPanels(DATA, colorscale); } catch (e) { console.error('panels', e); }
  try { scenarios = createScenarioController(ctx, DATA, vessels); } catch (e) { console.error('scenarios', e); }
  try { tumors = createTumors(ctx, DATA, vessels, flow, scenarios); if (scenarios) scenarios.setTumors(tumors); } catch (e) { console.error('tumors', e); }
  try { journey = createJourney(ctx, DATA, vessels, flow); } catch (e) { console.error('journey', e); }
  try { simlab = createSimLab(ctx, DATA, vessels, flow, tumors); } catch (e) { console.error('simlab', e); }
  try { buildUI(ctx, DATA, { vessels, flow, panels, scenarios, journey, tumors, simlab, anatomy }); } catch (e) { console.error('ui', e); }

  // Organs are pickable once their mesh has loaded; the raycaster reads this list live.
  if (anatomy && vessels) {
    anatomy.ready.then(() => { for (const m of anatomy.pickables) vessels.pickables.push(m); });
  }

  // ── Resize ──
  function onResize() {
    width = container.clientWidth || window.innerWidth;
    height = container.clientHeight || window.innerHeight;
    camera.aspect = width / height; camera.updateProjectionMatrix();
    renderer.setSize(width, height); composer.setSize(width, height);
  }
  window.addEventListener('resize', onResize);

  // ── FPS-adaptive quality guard: drop bloom → pixelRatio. (flow.js owns particle COUNT via its
  //    own fps governor — single count authority, so the guard never touches particle count.) ──
  let fpsAccum = 0, fpsFrames = 0, lowStreak = 0, guardStage = 0;
  function guard(fps) {
    if (fps >= 28 || fps === 0) { lowStreak = 0; return; }
    if (++lowStreak < 90) return; // ~1.5 s sustained
    lowStreak = 0;
    if (guardStage === 0) { bloom.enabled = false; guardStage = 1; }
    else if (guardStage === 1) { renderer.setPixelRatio(1); composer.setPixelRatio(1); flow && flow.setPixelRatio(1); guardStage = 2; }
  }

  // ── Establishing shot ──
  const skipBtn = document.getElementById('skip-intro');
  const seenIntro = sessionStorage.getItem('hl_seen_intro') === '1';
  let intro = !reducedMotion && !seenIntro;
  let introT = 0;
  const introFrom = new THREE.Vector3();
  function setIntroFrom() {
    introFrom.copy(framedPos).multiplyScalar(1.7).add(new THREE.Vector3(0, 0, 30));
  }
  setIntroFrom();
  camera.position.copy(intro ? introFrom : framedPos);

  // Re-frame on the real body once it arrives, unless the viewer has already taken the camera.
  let userMovedCamera = false;
  controls.addEventListener('start', () => { userMovedCamera = true; });
  if (anatomy) {
    anatomy.ready.then(() => {
      const box = anatomy.bounds();
      if (!box || userMovedCamera) return;
      frameOn(box);
      setIntroFrom();
      camera.position.copy(intro ? introFrom : framedPos);
      controls.update();
    });
  }
  function endIntro() {
    intro = false; camera.position.copy(framedPos); controls.update();
    if (skipBtn) skipBtn.hidden = true;
    sessionStorage.setItem('hl_seen_intro', '1');
    document.body.classList.remove('intro-running');
  }
  if (intro) {
    document.body.classList.add('intro-running');
    if (skipBtn) { skipBtn.hidden = false; skipBtn.addEventListener('click', endIntro); }
    window.addEventListener('keydown', (e) => { if (intro && (e.key === 'Escape' || e.key === ' ')) endIntro(); }, { once: false });
  }

  // ── Reveal UI, hide loader ──
  document.getElementById('ui').hidden = false;
  const loading = document.getElementById('loading');
  if (loading) loading.classList.add('done');

  // ── Render loop ──
  const clock = new THREE.Clock();
  let readyFrames = 0;
  // ALWAYS through the composer, even with bloom off.
  //
  // This used to be `(bloom.enabled ? composer : renderer).render(...)`, and that ternary was
  // silently changing the data. The vessel, tissue and flow materials are raw ShaderMaterials
  // that write gl_FragColor with no <tonemapping_fragment> / <colorspace_fragment> include, so
  // renderer.render() sends their values to the framebuffer untouched while composer.render()
  // sends them through OutputPass's tone map and colour-space encode. Two different colours for
  // one WSS value — and the fps guard below flips between them at runtime, so frame rate decided
  // what shade of shear a viewer saw. Measured at ΔE 19.9 median, ~36% of a decade of WSS
  // (tools/color-probe.mjs, tasks/color-fidelity-report.md).
  //
  // Nothing is lost by always composing: EffectComposer skips any pass whose `enabled` is false,
  // so `bloom.enabled = false` still buys back the bloom pass's cost for the fps guard — it just
  // no longer changes the colour pipeline on its way past.
  function renderFrame() { composer.render(); }

  // Initial synchronous paint so a frame exists even if rAF is throttled (e.g. background tab).
  renderFrame();
  state.sceneReady = true; window.__sceneReady = true;

  // Debug/test surface: drive the sim and assert state without depending on rAF.
  window.__hl = {
    renderOnce: renderFrame,
    tick(dt = 0.016) { for (const fn of updaters) fn(dt, clock.elapsedTime); controls.update(); renderFrame(); },
    setSize(w, h) { renderer.setSize(w, h, false); composer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix(); },
    frame() { endIntro(); },
    scene, camera, renderer, controls, composer, bloom, scenarios, journey, flow, vessels, panels, tumors, simlab,
    anatomy, framedPos,
    // colorscale + data are exposed so tools/color-probe.mjs can compare what a vessel actually
    // renders as against what the legend says that WSS value should look like. They are the
    // reference side of that comparison, so the probe must read them from here rather than
    // re-deriving the ramp — a re-derivation could agree with a drifted render and prove nothing.
    colorscale, data: DATA,
  };

  function animate() {
    requestAnimationFrame(animate);
    const dt = Math.min(clock.getDelta(), 0.05);

    if (intro) {
      introT += dt / 2.5;
      const e = easeInOut(Math.min(introT, 1));
      camera.position.lerpVectors(introFrom, framedPos, e);
      if (introT >= 1) endIntro();
    }

    for (const fn of updaters) fn(dt, clock.elapsedTime);
    controls.update();
    renderFrame();

    // fps
    fpsAccum += dt; fpsFrames++;
    if (fpsAccum >= 0.5) {
      const fps = fpsFrames / fpsAccum;
      window.__fps = state.fps = Math.round(fps);
      guard(fps); fpsAccum = 0; fpsFrames = 0;
    }
    readyFrames++;
  }
  animate();
}

function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

function computeBounds(data) {
  const box = new THREE.Box3();
  const v = new THREE.Vector3();
  for (const ves of data.vessels) for (const p of ves.path) box.expandByPoint(v.set(p[0], p[1], p[2]));
  for (const b of data.beds) box.expandByPoint(v.set(b.center[0], b.center[1], b.center[2]));
  return box;
}

try { init(); } catch (e) { fail('Could not start the visualization: ' + (e && e.message ? e.message : e)); }
