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
  scene.fog = new THREE.Fog(BG, 180, 360);

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

  // Lighting (mainly for the MeshStandard fallback + ghost body; emissive does the rest).
  scene.add(new THREE.AmbientLight(0x9fb4d0, 0.55));
  const key = new THREE.DirectionalLight(0xffffff, 0.5); key.position.set(60, 80, 120); scene.add(key);
  const rim = new THREE.DirectionalLight(0x4060a0, 0.35); rim.position.set(-80, -60, 40); scene.add(rim);

  const colorscale = createColorScale(DATA);

  // ── Ghost body silhouette (back-face x-ray; hides seams, drawn before vessels) ──
  buildGhostBody(scene);

  // ── Heart (pulsing) ──
  const heart = buildHeart(scene, DATA);

  // ── Bounding box → frame the camera on the vasculature ──
  const bbox = computeBounds(DATA);
  const center = bbox.getCenter(new THREE.Vector3());
  const size = bbox.getSize(new THREE.Vector3());
  const radius = Math.max(size.x, size.z) * 0.62;
  const framedDist = radius / Math.tan((camera.fov * Math.PI) / 360) * 1.05;
  controls.target.copy(center);
  const framedPos = new THREE.Vector3(center.x + framedDist * 0.62, center.y - framedDist * 0.72, center.z + framedDist * 0.16);

  // Post-processing
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(width, height), 0.72, 0.4, 0.85);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  composer.setPixelRatio(renderer.getPixelRatio());
  composer.setSize(width, height);

  // Shared app context handed to every module.
  const updaters = [];
  const ctx = {
    THREE, scene, camera, renderer, controls, composer, bloom, colorscale, data: DATA,
    container, state, reducedMotion, coarsePointer, lowMemory,
    registerUpdate: (fn) => updaters.push(fn),
    setBloom: (on) => { bloom.enabled = on; },
  };

  // ── Build subsystems (each guarded so one failure can't blank the app) ──
  let vessels, flow, panels, scenarios, journey;
  try { vessels = buildVasculature(ctx, DATA); } catch (e) { console.error('vessels', e); }
  try { flow = buildFlow(ctx, DATA); } catch (e) { console.error('flow', e); }
  try { panels = buildPanels(DATA, colorscale); } catch (e) { console.error('panels', e); }
  try { scenarios = createScenarioController(ctx, DATA, vessels); } catch (e) { console.error('scenarios', e); }
  try { journey = createJourney(ctx, DATA, vessels, flow); } catch (e) { console.error('journey', e); }
  try { buildUI(ctx, DATA, { vessels, flow, panels, scenarios, journey }); } catch (e) { console.error('ui', e); }

  // ── Resize ──
  function onResize() {
    width = container.clientWidth || window.innerWidth;
    height = container.clientHeight || window.innerHeight;
    camera.aspect = width / height; camera.updateProjectionMatrix();
    renderer.setSize(width, height); composer.setSize(width, height);
  }
  window.addEventListener('resize', onResize);

  // ── FPS-adaptive quality guard: drop bloom → particles → pixelRatio ──
  let fpsAccum = 0, fpsFrames = 0, lowStreak = 0, guardStage = 0;
  function guard(fps) {
    if (fps >= 28 || fps === 0) { lowStreak = 0; return; }
    if (++lowStreak < 90) return; // ~1.5 s sustained
    lowStreak = 0;
    if (guardStage === 0) { bloom.enabled = false; guardStage = 1; }
    else if (guardStage === 1 && flow) { flow.setDensity('low'); guardStage = 2; }
    else if (guardStage === 2) { renderer.setPixelRatio(1); composer.setPixelRatio(1); guardStage = 3; }
  }

  // ── Establishing shot ──
  const skipBtn = document.getElementById('skip-intro');
  const seenIntro = sessionStorage.getItem('hl_seen_intro') === '1';
  let intro = !reducedMotion && !seenIntro;
  let introT = 0;
  const introFrom = framedPos.clone().multiplyScalar(1.7).add(new THREE.Vector3(0, 0, 30));
  camera.position.copy(intro ? introFrom : framedPos);
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
  function renderFrame() { (bloom.enabled ? composer : renderer).render(scene, camera); }

  // Initial synchronous paint so a frame exists even if rAF is throttled (e.g. background tab).
  renderFrame();
  state.sceneReady = true; window.__sceneReady = true;

  // Debug/test surface: drive the sim and assert state without depending on rAF.
  window.__hl = {
    renderOnce: renderFrame,
    tick(dt = 0.016) { for (const fn of updaters) fn(dt, clock.elapsedTime); controls.update(); renderFrame(); },
    setSize(w, h) { renderer.setSize(w, h, false); composer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix(); },
    frame() { endIntro(); },
    scene, camera, renderer, controls, composer, bloom, scenarios, journey, flow, vessels, panels,
    framedPos,
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

    if (heart && !reducedMotion) heart.update(clock.elapsedTime);
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

function buildGhostBody(scene) {
  const parts = [
    [[0, -2, 12], [17, 11, 28]], [[0, 0, 73], [9, 9, 11]], [[0, -1, 58], [5.5, 5, 7]],
    [[20, -1, 38], [4.5, 4, 14]], [[24, 0, 12], [3.5, 3, 13]],
    [[-20, -1, 38], [4.5, 4, 14]], [[-24, 0, 12], [3.5, 3, 13]],
    [[8, -1, -30], [7, 6.5, 22]], [[8, 0, -65], [5, 4.5, 18]],
    [[-8, -1, -30], [7, 6.5, 22]], [[-8, 0, -65], [5, 4.5, 18]],
    [[0, -2, -10], [14, 10, 8]], [[16, -1, 48], [6, 5, 5]], [[-16, -1, 48], [6, 5, 5]],
  ];
  const mat = new THREE.MeshBasicMaterial({
    color: 0x6f86b0, transparent: true, opacity: 0.06, side: THREE.BackSide,
    depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const group = new THREE.Group();
  group.renderOrder = -1;
  for (const [c, r] of parts) {
    const geo = new THREE.SphereGeometry(1, 24, 18);
    const m = new THREE.Mesh(geo, mat);
    m.position.set(c[0], c[1], c[2]); m.scale.set(r[0], r[1], r[2]);
    group.add(m);
  }
  scene.add(group);
}

function buildHeart(scene, data) {
  const L = data.landmarks.heart;
  const geo = new THREE.SphereGeometry(1, 28, 20);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x8a1a1a, emissive: 0xb4221e, emissiveIntensity: 0.9,
    roughness: 0.5, metalness: 0.0, transparent: true, opacity: 0.92,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(L.pos[0], L.pos[1], L.pos[2]);
  const base = new THREE.Vector3(L.radii[0], L.radii[1], L.radii[2]);
  mesh.scale.copy(base);
  scene.add(mesh);
  return {
    mesh,
    update(t) {
      // double-thump heartbeat ~1 Hz
      const beat = Math.pow(Math.sin(t * Math.PI) * 0.5 + 0.5, 8);
      const s = 1 + beat * 0.07;
      mesh.scale.copy(base).multiplyScalar(s);
      mat.emissiveIntensity = 0.8 + beat * 0.5;
    },
  };
}

try { init(); } catch (e) { fail('Could not start the visualization: ' + (e && e.message ? e.message : e)); }
