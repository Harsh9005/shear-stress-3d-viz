// flow.js — high-resolution GPU "stateless" particle flow.
// Each particle's world position is computed every frame in a vertex shader from uTime + the
// particle's static seeds, sampling per-vessel centerline + meta packed into RGBA32F textures.
// Physics (illustrative, not CFD): a parabolic (Poiseuille) velocity profile + shear-driven
// margination (drift to walls in LOW shear) + schematic disturbed flow near tumors/stenosis.
import * as THREE from 'three';

const MAX_SAMPLES = 128;                       // centerline samples per vessel (texture width)
const TIERS = { off: 0, low: 8000, med: 30000, high: 80000 };
const FLOOR = 3000;                            // governor never drops below this (unless 'off')

function meanWss(v) { return (v.wss[0] + v.wss[1]) / 2; }

const VERT = /* glsl */`
in float aVessel; in float aSeed; in float aAngle; in float aRadialSeed;
uniform sampler2D uCenterline; uniform sampler2D uMeta;
uniform float uTime, uSpeedScale, uSizeScale, uPixelRatio, uMaxPointSize, uStreak;
out float vStop; out float vAlpha; out float vFast;
out vec2 vDir;                                 // screen-space flow direction, for the streak

vec3 sampleCenter(int v, float s) {            // s in [0, MAX-1]; manual lerp (NEAREST float tex)
  int i0 = int(floor(s));
  int i1 = min(i0 + 1, ${MAX_SAMPLES} - 1);
  float f = s - float(i0);
  vec3 p0 = texelFetch(uCenterline, ivec2(i0, v), 0).xyz;
  vec3 p1 = texelFetch(uCenterline, ivec2(i1, v), 0).xyz;
  return mix(p0, p1, f);
}
void main() {
  int v = int(aVessel + 0.5);
  vec4 m = texelFetch(uMeta, ivec2(0, v), 0);  // (radius, wssStop, baseSpeed, disturbance)
  float radius = m.x, wssStop = m.y, baseSpeed = m.z, disturb = m.w;
  vStop = wssStop;

  // Poiseuille velocity profile: core lanes fast, wall lanes slow (0.2 floor = illustrative, true no-slip is 0).
  float prof = 0.2 + 0.8 * (1.0 - aRadialSeed * aRadialSeed);
  float speed = baseSpeed * uSpeedScale * prof;
  float t = fract(aSeed + uTime * speed);

  // Shear-driven margination: in LOW shear, drift toward the wall over residence time t.
  float marg = clamp(1.0 - 1.4 * wssStop, 0.0, 1.0);
  float rEff = mix(aRadialSeed, 1.0, marg * t);

  float s = t * float(${MAX_SAMPLES} - 1);
  vec3 pos = sampleCenter(v, s);
  vec3 pa = sampleCenter(v, clamp(s - 1.0, 0.0, float(${MAX_SAMPLES} - 1)));
  vec3 pb = sampleCenter(v, clamp(s + 1.0, 0.0, float(${MAX_SAMPLES} - 1)));
  vec3 T = normalize(pb - pa + vec3(1e-5));
  vec3 up = abs(T.z) > 0.99 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 0.0, 1.0);  // Z-up app: avoid degenerate frame
  vec3 N = normalize(cross(up, T));
  vec3 B = cross(T, N);
  vec3 offset = rEff * radius * (cos(aAngle) * N + sin(aAngle) * B);

  if (disturb > 0.5) {                         // schematic disturbed flow (cosmetic, fixed amplitude)
    float sw = sin(uTime * 3.0 + t * 12.0 + aAngle);
    offset += (0.4 * radius) * sw * (sin(aAngle) * N - cos(aAngle) * B);
  }

  vAlpha = smoothstep(0.0, 0.05, t) * (1.0 - smoothstep(0.95, 1.0, t));  // hide wrap teleport
  vFast = prof;                                  // core lanes are brighter as well as faster

  vec4 mv = modelViewMatrix * vec4(pos + offset, 1.0);
  gl_Position = projectionMatrix * mv;

  // Screen-space flow direction, so the fragment shader can draw a streak that lies ALONG the
  // vessel instead of a round dot. A round sprite reads as a static glow; a streak reads as
  // something moving, which is the whole point of drawing particles at all.
  vec4 clipAhead = projectionMatrix * (modelViewMatrix * vec4(pos + offset + T, 1.0));
  vec2 here = gl_Position.xy / max(gl_Position.w, 1e-4);
  vec2 ahead = clipAhead.xy / max(clipAhead.w, 1e-4);
  vec2 d = ahead - here;
  vDir = length(d) > 1e-6 ? normalize(d) : vec2(1.0, 0.0);

  // Elongating the sprite needs a bigger point to draw into, or the streak is clipped square.
  // The stretch goes INSIDE the clamp: multiplying afterwards let a near-camera particle reach
  // several hundred pixels and paint a white gash across the view.
  gl_PointSize = clamp(uSizeScale * uPixelRatio * uStreak / -mv.z, 1.0, uMaxPointSize);
}`;

const FRAG = /* glsl */`
precision highp float;
in float vStop; in float vAlpha; in float vFast; in vec2 vDir;
uniform sampler2D uColorLUT; uniform float uParticleAlpha, uStreak;
out vec4 fragColor;
void main() {
  // Reshape the square point sprite into a capsule aligned with the flow: local.x runs down the
  // vessel and is stretched by uStreak, local.y is the vessel's width and stays tight.
  // (No backticks in here -- this whole shader is a JS template literal.)
  vec2 c = gl_PointCoord - 0.5;
  vec2 dir = normalize(vDir);
  vec2 local = vec2(dot(c, dir), dot(c, vec2(-dir.y, dir.x)));
  local.x /= uStreak;
  float d = dot(local, local) * 4.0;             // 0 at centre, 1 at the sprite edge
  if (d > 1.0) discard;

  vec3 col = texture(uColorLUT, vec2(clamp(vStop, 0.0, 1.0), 0.5)).rgb;

  // A hot core inside a coloured halo. The core is what survives the low bloom this scene now
  // runs, and it is what makes a particle read as a discrete cell in the stream rather than as
  // more of the tube it is inside.
  float halo = smoothstep(1.0, 0.0, d);
  float core = smoothstep(0.35, 0.0, d) * (0.35 + 0.65 * vFast);
  vec3 lit = mix(col, mix(col, vec3(1.0), 0.75), core);

  float a = (halo * 0.55 + core * 0.55) * vAlpha * uParticleAlpha;
  fragColor = vec4(lit * (1.0 + core * 0.30), a);
}`;

export function buildFlow(ctx, data) {
  const { THREE: T, scene, colorscale } = ctx;
  const nV = data.vessels.length;
  const idIndex = new Map(data.vessels.map((v, i) => [v.id, i]));

  // ── Centerline + meta float textures ──
  const cl = new Float32Array(MAX_SAMPLES * nV * 4);
  const meta = new Float32Array(nV * 4);
  const lengthFactor = new Float32Array(nV);
  for (let vi = 0; vi < nV; vi++) {
    const vsl = data.vessels[vi];
    const pts = vsl.path.map((p) => new T.Vector3(p[0], p[1], p[2]));
    const curve = new T.CatmullRomCurve3(pts, false, 'centripetal');
    const sp = curve.getSpacedPoints(MAX_SAMPLES - 1);     // → MAX_SAMPLES points
    for (let i = 0; i < MAX_SAMPLES; i++) {
      const o = (vi * MAX_SAMPLES + i) * 4;
      cl[o] = sp[i].x; cl[o + 1] = sp[i].y; cl[o + 2] = sp[i].z; cl[o + 3] = 1;
    }
    const stop = colorscale.wssToStop(meanWss(vsl));
    // Speed is set in scene units per second and then converted to fraction-of-vessel per
    // second, so a particle physically moves faster where shear is higher rather than merely
    // completing whatever vessel it is in at the same rate. Before this, a short coronary and
    // the whole descending aorta were traversed in the same time, which read as the aorta being
    // fast and everything else crawling. Illustrative, like the rest of the flow model.
    const lengthUnits = Math.max(curve.getLength(), 1e-3);
    const unitsPerSecond = 5 + 34 * stop;
    const baseSpeed = Math.min(unitsPerSecond / lengthUnits, 0.9);
    meta[vi * 4] = vsl.radius; meta[vi * 4 + 1] = stop; meta[vi * 4 + 2] = baseSpeed; meta[vi * 4 + 3] = 0;
    lengthFactor[vi] = Math.max(0.35, Math.min(1, lengthUnits / 60));
  }
  const centerlineTex = new T.DataTexture(cl, MAX_SAMPLES, nV, T.RGBAFormat, T.FloatType);
  centerlineTex.minFilter = centerlineTex.magFilter = T.NearestFilter; centerlineTex.needsUpdate = true;
  const metaTex = new T.DataTexture(meta, 1, nV, T.RGBAFormat, T.FloatType);
  metaTex.minFilter = metaTex.magFilter = T.NearestFilter; metaTex.needsUpdate = true;

  // ── Colour LUT (RGBA8, LINEAR ok in WebGL2) ──
  function buildLUT() {
    const lut = new Uint8Array(256 * 4);
    for (let i = 0; i < 256; i++) {
      const [r, g, b] = colorscale.rgbAtStop(i / 255);
      lut[i * 4] = r; lut[i * 4 + 1] = g; lut[i * 4 + 2] = b; lut[i * 4 + 3] = 255;
    }
    return lut;
  }
  const colorLUT = new T.DataTexture(buildLUT(), 256, 1, T.RGBAFormat, T.UnsignedByteType);
  colorLUT.minFilter = colorLUT.magFilter = T.LinearFilter; colorLUT.needsUpdate = true;

  // ── Particle attributes, emitted length-weighted round-robin so any prefix is representative ──
  const N = TIERS.high;
  const aVessel = new Float32Array(N), aSeed = new Float32Array(N);
  const aAngle = new Float32Array(N), aRadialSeed = new Float32Array(N);
  const pos = new Float32Array(N * 3); // dummy position attribute (count/bounds); unused in shader
  let totalW = 0; for (let i = 0; i < nV; i++) totalW += lengthFactor[i];
  const frac = Array.from(lengthFactor, (w) => w / totalW);
  const emitted = new Float32Array(nV);
  for (let i = 0; i < N; i++) {
    let best = 0, bestScore = -Infinity;
    for (let v = 0; v < nV; v++) { const sc = frac[v] * (i + 1) - emitted[v]; if (sc > bestScore) { bestScore = sc; best = v; } }
    emitted[best]++;
    aVessel[i] = best; aSeed[i] = Math.random();
    aAngle[i] = Math.random() * Math.PI * 2; aRadialSeed[i] = Math.sqrt(Math.random());
  }

  const geo = new T.BufferGeometry();
  geo.setAttribute('position', new T.BufferAttribute(pos, 3));
  geo.setAttribute('aVessel', new T.BufferAttribute(aVessel, 1));
  geo.setAttribute('aSeed', new T.BufferAttribute(aSeed, 1));
  geo.setAttribute('aAngle', new T.BufferAttribute(aAngle, 1));
  geo.setAttribute('aRadialSeed', new T.BufferAttribute(aRadialSeed, 1));

  const uniforms = {
    uCenterline: { value: centerlineTex }, uMeta: { value: metaTex }, uColorLUT: { value: colorLUT },
    uTime: { value: 0 }, uSpeedScale: { value: 1 }, uSizeScale: { value: 300 },
    uPixelRatio: { value: ctx.renderer.getPixelRatio() }, uMaxPointSize: { value: 110 },
    uParticleAlpha: { value: 0.9 },
    // How far a particle is stretched along the flow. 1.0 is the old round dot.
    uStreak: { value: 3.4 },
  };
  const mat = new T.ShaderMaterial({
    glslVersion: T.GLSL3, vertexShader: VERT, fragmentShader: FRAG, uniforms,
    transparent: true, blending: T.AdditiveBlending, depthTest: true, depthWrite: false,
  });
  const points = new T.Points(geo, mat);
  points.frustumCulled = false;     // positions are shader-computed; default bbox would cull
  scene.add(points);

  // ── Count authority: setDensity = user ceiling; internal fps governor scales within it ──
  let tier = (ctx.coarsePointer || ctx.lowMemory) ? 'off' : 'med';
  let ceiling = TIERS[tier];
  let current = ceiling;
  function applyCount() {
    points.visible = tier !== 'off' && current > 0;
    geo.setDrawRange(0, Math.max(0, Math.min(current, N)));
    // Tier-invariant luminance, and streak-invariant too: an elongated sprite covers uStreak
    // times the area of the round one it replaced, so without dividing it through, turning on
    // streaks alone multiplies the total light the flow emits and blows the scene out.
    uniforms.uParticleAlpha.value = current > 0
      ? (0.9 / Math.sqrt(current / 8000)) / uniforms.uStreak.value : 0;
    ctx.state.particleCount = points.visible ? current : 0;
  }
  applyCount();

  // ── Disturbance (union of sources) → metaTex alpha ──
  const disturbBy = new Map(); // source → Set(vesselId)
  function recomputeDisturb() {
    const on = new Set();
    for (const set of disturbBy.values()) for (const id of set) on.add(id);
    for (let v = 0; v < nV; v++) meta[v * 4 + 3] = 0;
    for (const id of on) { const v = idIndex.get(id); if (v != null) meta[v * 4 + 3] = 1; }
    metaTex.needsUpdate = true;
  }

  let govAccum = 0;
  ctx.registerUpdate((dt, elapsed) => {
    uniforms.uTime.value = elapsed;
    govAccum += dt;
    if (govAccum >= 0.5) {
      govAccum = 0;
      const fps = ctx.state.fps || 0;
      if (tier !== 'off') {
        if (fps > 0 && fps < 28) current = Math.max(FLOOR, Math.floor(current * 0.7));
        else if (fps > 52 && current < ceiling) current = Math.min(ceiling, Math.ceil(current * 1.15));
        applyCount();
      }
    }
  });

  return {
    group: points,
    setEnabled(on) { tier = on ? (tier === 'off' ? 'med' : tier) : 'off'; ceiling = TIERS[tier]; current = ceiling; applyCount(); },
    isEnabled() { return points.visible && tier !== 'off'; },
    setDensity(t) { tier = (t in TIERS) ? t : 'med'; ceiling = TIERS[tier]; current = ceiling; applyCount(); colorLUT.needsUpdate = true; },
    getDensity() { return tier; },
    setSpeedScale(s) { uniforms.uSpeedScale.value = s; },
    requestPerfRelief() { if (tier !== 'off') { current = Math.max(FLOOR, Math.floor(current * 0.6)); applyCount(); } },
    refreshColorLUT() { colorLUT.image.data.set(buildLUT()); colorLUT.needsUpdate = true; },
    setColorblind() { colorscale && this.refreshColorLUT(); },
    setPixelRatio(r) { uniforms.uPixelRatio.value = r; },
    setStreak(v) { uniforms.uStreak.value = Math.max(1, v); },
    getStreak() { return uniforms.uStreak.value; },
    setDisturbedVessels(source, idSet) { disturbBy.set(source, new Set(idSet || [])); recomputeDisturb(); },
    getDisturbedCount() { let n = 0; for (let v = 0; v < nV; v++) if (meta[v * 4 + 3] > 0.5) n++; return n; },
  };
}
