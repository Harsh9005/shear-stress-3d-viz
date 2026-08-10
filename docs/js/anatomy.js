// anatomy.js — the real human body: skin surface, organs and heart, loaded from GLB assets
// derived from BodyParts3D (CC BY-SA 2.1 Japan; see docs/assets/anatomy/LICENSE).
//
// Replaces the fourteen overlapping ellipsoids and the sphere-shaped heart and organs that the
// scene used before. The meshes arrive already in scene coordinates — build/anatomy/ does the
// fitting offline — so nothing here transforms geometry.
//
// Rendering follows a medical-illustration reading rather than the x-ray glow the vessels use:
// tissue is lit and semi-opaque, with Fresnel-weighted transparency so a surface facing you
// stays see-through while its silhouette edge holds. A clipped window over the torso opens the
// thorax and abdomen so the vasculature inside is read directly rather than through skin.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const ASSETS = 'assets/anatomy/';

// Three fixed lights baked into the shader. Doing the lighting here rather than through
// three's light uniforms keeps these materials independent of the scene's light rig, which
// exists mainly for the vessels, and keeps tissue looking the same from every angle.
const LIGHT_DIRS = `
  const vec3 KEY  = normalize(vec3( 0.45, -0.75,  0.55));
  const vec3 FILL = normalize(vec3(-0.65, -0.35,  0.10));
  const vec3 RIM  = normalize(vec3( 0.10,  0.85, -0.35));
`;

const TISSUE_VERT = `
varying vec3 vNormalW;
varying vec3 vViewDir;
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vNormalW = normalize(mat3(modelMatrix) * normal);
  vViewDir = normalize(cameraPosition - wp.xyz);
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

// Two-sided lighting: interior faces seen through the cutaway must read as lit tissue, not as
// black holes, so the normal is flipped toward the viewer before shading.
const TISSUE_FRAG = `
uniform vec3 uColor;
uniform float uOpacity;
uniform float uFresnel;    // how strongly grazing angles gain opacity
uniform float uAmbient;
uniform float uSpecular;
varying vec3 vNormalW;
varying vec3 vViewDir;
${LIGHT_DIRS}
void main() {
  vec3 V = normalize(vViewDir);
  vec3 N = normalize(vNormalW);
  if (dot(N, V) < 0.0) N = -N;

  float key  = max(dot(N, KEY), 0.0);
  float fill = max(dot(N, FILL), 0.0) * 0.45;
  float rim  = max(dot(N, RIM), 0.0) * 0.35;
  vec3 lit = uColor * (uAmbient + key + fill) + vec3(0.55, 0.60, 0.72) * rim;

  float spec = pow(max(dot(reflect(-KEY, N), V), 0.0), 28.0) * uSpecular;
  lit += vec3(spec);

  float fres = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 2.0);
  float alpha = clamp(uOpacity + fres * uFresnel, 0.0, 1.0);
  gl_FragColor = vec4(lit, alpha);
}`;

function tissueMaterial({ color, opacity, fresnel = 0.55, ambient = 0.28, specular = 0.25,
  clippingPlanes = null, depthWrite = false, side = THREE.DoubleSide }) {
  const mat = new THREE.ShaderMaterial({
    vertexShader: TISSUE_VERT,
    fragmentShader: TISSUE_FRAG,
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uOpacity: { value: opacity },
      uFresnel: { value: fresnel },
      uAmbient: { value: ambient },
      uSpecular: { value: specular },
    },
    transparent: true,
    side,
    depthWrite,
  });
  if (clippingPlanes) {
    mat.clippingPlanes = clippingPlanes;
    mat.clipIntersection = true;   // see makeCutaway: the planes describe a window, not a slab
  }
  return mat;
}

// Tissue colours: conventional anatomical-illustration hues, muted so that WSS colour on the
// vessels stays the only saturated thing on screen. The colour scale is the data; nothing here
// may compete with it.
const ORGAN_STYLE = {
  brain:        { color: 0xc9a2a6, opacity: 0.30, label: 'Brain' },
  right_lung:   { color: 0xc08a92, opacity: 0.20, label: 'R. Lung' },
  left_lung:    { color: 0xc08a92, opacity: 0.20, label: 'L. Lung' },
  liver:        { color: 0x8e4a3c, opacity: 0.38, label: 'Liver' },
  spleen:       { color: 0x7a3a4c, opacity: 0.38, label: 'Spleen' },
  pancreas:     { color: 0xc2a06a, opacity: 0.34, label: 'Pancreas' },
  right_kidney: { color: 0x9c4f42, opacity: 0.40, label: 'R. Kidney' },
  left_kidney:  { color: 0x9c4f42, opacity: 0.40, label: 'L. Kidney' },
};

const BODY_COLOR = 0xcbb6a6;
const HEART_COLOR = 0x9d2b26;

/**
 * A window cut into the anterior torso.
 *
 * Three planes with `clipIntersection = true`: a fragment survives if it satisfies ANY of them,
 * so it is removed only where all three fail at once — anterior AND below the shoulders AND
 * above the pelvis. That intersection is the window; a single plane would slice the whole body
 * in half, head and legs included.
 */
function makeCutaway(yCut, zTop, zBottom) {
  return [
    new THREE.Plane(new THREE.Vector3(0, 1, 0), -yCut),      // keep posterior
    new THREE.Plane(new THREE.Vector3(0, 0, 1), -zTop),      // keep above the window
    new THREE.Plane(new THREE.Vector3(0, 0, -1), zBottom),   // keep below the window
  ];
}

export function createAnatomy(ctx, data) {
  const { THREE: T, scene, renderer } = ctx;
  // Organ notes live in the data layer, keyed by the same ids the GLB nodes use, so the tooltip
  // text has exactly one home.
  const notes = new Map((data && data.organs ? data.organs : []).map((o) => [o.id || o.name, o.note]));
  renderer.localClippingEnabled = true;

  const group = new T.Group();
  group.name = 'anatomy';
  scene.add(group);

  const cutaway = makeCutaway(-1.5, 46, -14);
  const pickables = [];
  const state = { body: null, organs: new Map(), heart: null, loaded: false, cutaway: true };

  // Front faces only. Transparent draws are not depth-sorted, so a double-sided body stacks
  // several layers per pixel — front torso, back torso, an arm, a hand — and the alpha
  // accumulates into a solid mass however low the per-layer value is set. Drawing only the
  // surface facing the viewer gives roughly one layer, which is what makes the organs and
  // vessels inside legible; it is also what makes the torso cutaway mean something, since the
  // window then removes the very surface you would have been looking through.
  const bodyMaterial = tissueMaterial({
    color: BODY_COLOR, opacity: 0.030, fresnel: 0.20, ambient: 0.34, specular: 0.10,
    side: T.FrontSide, clippingPlanes: cutaway,
  });

  const loader = new GLTFLoader();
  const load = (file) => new Promise((resolve, reject) => {
    loader.load(ASSETS + file, (gltf) => resolve(gltf), undefined, (err) => reject(err));
  });

  /**
   * Meshes in a loaded glTF scene, collected before anything is reparented.
   *
   * Calling group.add() from inside traverse() mutates the children array being walked, so the
   * walk skips every second node — that silently loaded four of the eight organs.
   */
  function meshesOf(gltf) {
    const out = [];
    gltf.scene.traverse((o) => { if (o.isMesh) out.push(o); });
    return out;
  }

  function addBody(gltf) {
    meshesOf(gltf).forEach((o) => {
      o.material = bodyMaterial;
      // Drawn BEFORE the vessels and organs. Painting skin over them instead washes every
      // interior structure toward skin colour: transparent draws blend, so whatever is drawn
      // last tints everything behind it. Behind, the body still reads as a body through its
      // Fresnel-lit silhouette, and the structures the visualization is about stay crisp.
      o.renderOrder = -2;
      o.userData = { kind: 'body', name: 'Body surface' };
      state.body = o;
      group.add(o);
    });
  }

  function addOrgans(gltf) {
    meshesOf(gltf).forEach((o) => {
      const key = (o.name || '').replace(/[^a-z_]/gi, '').toLowerCase();
      const style = ORGAN_STYLE[key] || ORGAN_STYLE[o.parent?.name] || null;
      if (!style) return;
      o.material = tissueMaterial({ color: style.color, opacity: style.opacity, fresnel: 0.4 });
      o.renderOrder = 8;
      o.userData = {
        kind: 'organ', id: key, name: style.label,
        note: notes.get(key) || notes.get(style.label) || '',
      };
      state.organs.set(key, o);
      pickables.push(o);
      group.add(o);
    });
  }

  function addHeart(gltf) {
    const mat = tissueMaterial({
      color: HEART_COLOR, opacity: 0.72, fresnel: 0.3, ambient: 0.34, specular: 0.35,
      depthWrite: true,
    });
    meshesOf(gltf).forEach((o) => {
      o.material = mat;
      o.renderOrder = 6;
      o.userData = {
        kind: 'organ', id: 'heart', name: 'Heart',
        note: notes.get('heart') || 'Pumps the entire cardiac output through this landscape',
      };
      state.heart = o;
      pickables.push(o);
      group.add(o);
    });
    if (state.heart) {
      state.heart.userData.baseScale = state.heart.scale.clone();
      state.heart.userData.material = mat;
    }
  }

  // Loading is asynchronous and non-blocking: a slow or failed asset fetch must never stop the
  // visualization from starting, matching how every other subsystem here is guarded.
  const ready = Promise.allSettled([
    load('body.glb').then(addBody),
    load('organs.glb').then(addOrgans),
    load('heart.glb').then(addHeart),
  ]).then((results) => {
    const failed = results.filter((r) => r.status === 'rejected');
    if (failed.length) {
      console.warn('[anatomy] %d of 3 assets failed to load; continuing without them',
        failed.length, failed.map((f) => f.reason && f.reason.message));
    }
    state.loaded = results.some((r) => r.status === 'fulfilled');
    if (ctx.onAnatomyReady) ctx.onAnatomyReady(api);
    return state.loaded;
  });

  // The heartbeat that used to live on the sphere in main.js, now driving real cardiac geometry.
  ctx.registerUpdate((dt, t) => {
    const h = state.heart;
    if (!h || ctx.reducedMotion) return;
    const beat = Math.pow(Math.sin(t * Math.PI) * 0.5 + 0.5, 8);
    h.scale.copy(h.userData.baseScale).multiplyScalar(1 + beat * 0.035);
  });

  const api = {
    group, pickables, ready, bodyMaterial,
    isLoaded: () => state.loaded,
    organ: (id) => state.organs.get(id) || null,
    organIds: () => [...state.organs.keys()],
    setVisible(on) { group.visible = !!on; },
    setBodyVisible(on) { if (state.body) state.body.visible = !!on; },
    setCutaway(on) {
      state.cutaway = !!on;
      bodyMaterial.clippingPlanes = on ? cutaway : null;
      bodyMaterial.needsUpdate = true;
    },
    isCutaway: () => state.cutaway,
    setBodyOpacity(v) { bodyMaterial.uniforms.uOpacity.value = v; },
    /** World-space centroid of an organ — the honest source for bed and tumor-site anchors. */
    organCenter(id) {
      const m = state.organs.get(id);
      if (!m) return null;
      const box = new T.Box3().setFromObject(m);
      return box.getCenter(new T.Vector3());
    },
    bounds() {
      return group.children.length ? new T.Box3().setFromObject(group) : null;
    },
  };
  return api;
}
