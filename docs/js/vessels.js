// vessels.js — WSS-coloured tubes, sinusoidal beds and pathological hotspots.
// Organs are no longer stubbed here; anatomy.js loads the real meshes.
import * as THREE from 'three';

const VERT = `
varying vec3 vNormalW;
varying vec3 vViewDir;
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vNormalW = normalize(mat3(modelMatrix) * normal);
  vViewDir = normalize(cameraPosition - wp.xyz);
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

const FRAG = `
uniform vec3 uColor;
uniform float uEmissive;
uniform float uOpacity;
uniform float uDim;
uniform float uHi;
varying vec3 vNormalW;
varying vec3 vViewDir;
void main() {
  float fres = pow(1.0 - clamp(dot(normalize(vNormalW), normalize(vViewDir)), 0.0, 1.0), 2.4);
  vec3 col = uColor * (uEmissive + fres * 1.5 + uHi);
  col *= uDim;
  gl_FragColor = vec4(col, uOpacity);
}`;

function meanWss(v) { return (v.wss[0] + v.wss[1]) / 2; }

function glowTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.25, 'rgba(255,240,200,0.85)');
  grad.addColorStop(1, 'rgba(255,180,120,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
  const t = new THREE.Texture(c); t.needsUpdate = true; return t;
}

const HOTSPOT_COLORS = {
  plaque: new THREE.Color(1.0, 0.85, 0.2),
  stenosis: new THREE.Color(1.0, 0.25, 0.2),
  tumor: new THREE.Color(0.85, 0.3, 0.9),
};

export function buildBed(ctx, spec, wss, seed = 1337) {
  const { THREE: T, colorscale } = ctx;
  const n = 200;
  const pos = new Float32Array(n * 3);
  const col = new Float32Array(n * 3);
  const base = colorscale.colorAt(wss);
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  const [cx, cy, cz] = spec.center; const [sx, sy, sz] = spec.spread;
  for (let i = 0; i < n; i++) {
    const theta = rnd() * Math.PI * 2, phi = rnd() * Math.PI, r = Math.cbrt(rnd());
    pos[i * 3] = cx + r * sx * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = cy + r * sy * Math.sin(phi) * Math.sin(theta);
    pos[i * 3 + 2] = cz + r * sz * Math.cos(phi);
    const j = 0.85 + rnd() * 0.4;
    col[i * 3] = base.r * j; col[i * 3 + 1] = base.g * j; col[i * 3 + 2] = base.b * j;
  }
  const geo = new T.BufferGeometry();
  geo.setAttribute('position', new T.BufferAttribute(pos, 3));
  geo.setAttribute('color', new T.BufferAttribute(col, 3));
  const mat = new T.PointsMaterial({ size: 0.7, vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false });
  return new T.Points(geo, mat);
}

export function buildVasculature(ctx, data) {
  const { THREE: T, scene, colorscale } = ctx;
  const group = new T.Group();
  const pickGroup = new T.Group();
  const items = new Map();
  const pickables = [];

  for (const v of data.vessels) {
    const pts = v.path.map((p) => new T.Vector3(p[0], p[1], p[2]));
    const curve = new T.CatmullRomCurve3(pts, false, 'centripetal');
    const tubular = Math.max(32, Math.min(96, pts.length * 12));
    const radial = v.radius > 0.5 ? 12 : 10;
    const geo = new T.TubeGeometry(curve, tubular, v.radius, radial, false);
    const baseColor = colorscale.colorAt(meanWss(v));
    const mat = new T.ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG,
      uniforms: {
        uColor: { value: baseColor.clone() }, uEmissive: { value: 1.05 },
        uOpacity: { value: 1.0 }, uDim: { value: 1.0 }, uHi: { value: 0.0 },
      },
    });
    const mesh = new T.Mesh(geo, mat);
    mesh.userData = { kind: 'vessel', id: v.id, name: v.name, wss: v.wss, regime: v.regime, note: v.note, group: v.group, provenance: v.provenance, source: v.source };
    group.add(mesh);
    items.set(v.id, { mesh, mat, baseColor, vessel: v });

    // Invisible fat pick-proxy (so thin vessels are still hoverable).
    const pradius = Math.max(v.radius * 2.4, 0.55);
    const pgeo = new T.TubeGeometry(curve, Math.max(20, tubular / 2), pradius, 6, false);
    const pmat = new T.MeshBasicMaterial({ colorWrite: false, depthWrite: false });
    const pmesh = new T.Mesh(pgeo, pmat);
    pmesh.userData = mesh.userData;
    pickGroup.add(pmesh); pickables.push(pmesh);
  }

  // Default sinusoidal beds.
  const bedGroup = new T.Group();
  for (const b of data.beds) {
    const bed = buildBed(ctx, b, (b.wss[0] + b.wss[1]) / 2);
    bed.userData = { kind: 'bed', name: b.name, wss: b.wss, regime: b.regime, note: b.note };
    bedGroup.add(bed);
  }

  // Organs are real geometry now — anatomy.js loads them and registers them as pick targets.
  // The 0.7-radius spheres that used to stand in for them here have been removed.
  group.add(bedGroup);
  scene.add(group); scene.add(pickGroup);

  // ── Hotspot layer (rebuilt per scenario) ──
  const tex = glowTexture();
  const hotspotGroup = new T.Group();
  scene.add(hotspotGroup);
  const hotspotSprites = [];
  function showHotspots(list) {
    while (hotspotGroup.children.length) hotspotGroup.remove(hotspotGroup.children[0]);
    hotspotSprites.length = 0;
    for (const h of (list || [])) {
      const color = HOTSPOT_COLORS[h.kind] || new T.Color(1, 0.8, 0.3);
      const smat = new T.SpriteMaterial({ map: tex, color, transparent: true, opacity: 0.95, depthWrite: false, blending: T.AdditiveBlending });
      const sp = new T.Sprite(smat);
      sp.position.set(h.pos[0], h.pos[1], h.pos[2]);
      sp.scale.setScalar(h.kind === 'stenosis' ? 7 : 5.5);
      hotspotGroup.add(sp); hotspotSprites.push(sp);
    }
  }
  ctx.registerUpdate((dt, t) => {
    for (let i = 0; i < hotspotSprites.length; i++) {
      const s = 1 + Math.sin(t * 3 + i) * 0.16;
      hotspotSprites[i].material.opacity = 0.7 + Math.sin(t * 3 + i) * 0.25;
      const base = hotspotSprites[i].userData.base || (hotspotSprites[i].userData.base = hotspotSprites[i].scale.x);
      hotspotSprites[i].scale.setScalar(base * s);
    }
  });

  // ── Scenario bed layer (tumor) ──
  const scenarioBedGroup = new T.Group();
  scene.add(scenarioBedGroup);
  function setScenarioBeds(beds) {
    while (scenarioBedGroup.children.length) scenarioBedGroup.remove(scenarioBedGroup.children[0]);
    for (const b of (beds || [])) {
      const bed = buildBed(ctx, b, b.representativeWss || 1.0);
      scenarioBedGroup.add(bed);
    }
  }

  let highlighted = null;
  return {
    group, items, pickables,
    getBaseColor: (id) => items.get(id)?.baseColor,
    setVesselColor(id, color) { const it = items.get(id); if (it) it.mat.uniforms.uColor.value.copy(color); },
    setVesselDim(id, factor) { const it = items.get(id); if (it) it.mat.uniforms.uDim.value = factor; },
    setAllDim(factor) { for (const it of items.values()) it.mat.uniforms.uDim.value = factor; },
    resetColors() { for (const it of items.values()) { it.mat.uniforms.uColor.value.copy(it.baseColor); it.mat.uniforms.uDim.value = 1; } },
    recomputeColors() {
      for (const it of items.values()) {
        it.baseColor = colorscale.colorAt(meanWss(it.vessel));
        it.mat.uniforms.uColor.value.copy(it.baseColor);
      }
    },
    highlight(id) {
      if (highlighted && items.get(highlighted)) items.get(highlighted).mat.uniforms.uHi.value = 0;
      highlighted = id;
      if (id && items.get(id)) items.get(id).mat.uniforms.uHi.value = 0.8;
    },
    showHotspots, setScenarioBeds,
  };
}
