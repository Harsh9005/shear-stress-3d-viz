// flow.js — animated flow particles streaming along every vessel; speed & colour track local WSS.
// Each vessel is baked into an arc-length LUT once; particles advance a float index per frame (O(1)).
import * as THREE from 'three';

const TIERS = { off: 0, low: 20, med: 60, high: 150 };

function meanWss(v) { return (v.wss[0] + v.wss[1]) / 2; }

export function buildFlow(ctx, data) {
  const { THREE: T, scene, colorscale } = ctx;

  // Bake LUTs once.
  const luts = [];
  for (const v of data.vessels) {
    const pts = v.path.map((p) => new T.Vector3(p[0], p[1], p[2]));
    const curve = new T.CatmullRomCurve3(pts, false, 'centripetal');
    const len = curve.getLength();
    const samples = Math.max(24, Math.min(140, Math.round(len * 1.4)));
    const sp = curve.getSpacedPoints(samples);
    const arr = new Float32Array((samples + 1) * 3);
    for (let i = 0; i <= samples; i++) { arr[i * 3] = sp[i].x; arr[i * 3 + 1] = sp[i].y; arr[i * 3 + 2] = sp[i].z; }
    const c = colorscale.colorAt(meanWss(v));
    // higher WSS → faster; log-scaled so the 4-decade span reads as visibly different speeds
    const speed = 6 + 10 * Math.max(0.05, (Math.log10(meanWss(v)) + 1) / 4);
    luts.push({ arr, n: samples, color: c, speed, lengthFactor: Math.max(0.35, Math.min(1, len / 60)) });
  }

  const group = new T.Group();
  scene.add(group);
  let points = null, pVessel = null, pIdx = null, pSpeed = null, positions = null, count = 0;
  let tier = (ctx.coarsePointer || ctx.lowMemory) ? 'off' : 'med';

  function rebuild() {
    if (points) { group.remove(points); points.geometry.dispose(); points.material.dispose(); points = null; }
    const cap = TIERS[tier];
    if (cap === 0) { count = 0; ctx.state.particleCount = 0; return; }
    const per = [];
    let total = 0;
    for (const l of luts) { const k = Math.max(4, Math.round(cap * l.lengthFactor)); per.push(k); total += k; }
    count = total;
    positions = new Float32Array(total * 3);
    const colors = new Float32Array(total * 3);
    pVessel = new Int32Array(total); pIdx = new Float32Array(total); pSpeed = new Float32Array(total);
    let p = 0;
    for (let vi = 0; vi < luts.length; vi++) {
      const l = luts[vi];
      for (let k = 0; k < per[vi]; k++) {
        pVessel[p] = vi; pIdx[p] = Math.random() * l.n; pSpeed[p] = l.speed * (0.8 + Math.random() * 0.4);
        colors[p * 3] = l.color.r; colors[p * 3 + 1] = l.color.g; colors[p * 3 + 2] = l.color.b;
        p++;
      }
    }
    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.BufferAttribute(positions, 3).setUsage(T.DynamicDrawUsage));
    geo.setAttribute('color', new T.BufferAttribute(colors, 3));
    const mat = new T.PointsMaterial({ size: 0.55, vertexColors: true, transparent: true, opacity: 0.95, depthWrite: false, blending: T.AdditiveBlending });
    points = new T.Points(geo, mat);
    group.add(points);
    ctx.state.particleCount = total;
    writePositions();
  }

  const a = new T.Vector3(), b = new T.Vector3();
  function writePositions() {
    if (!points) return;
    for (let p = 0; p < count; p++) {
      const l = luts[pVessel[p]];
      let f = pIdx[p] % l.n; if (f < 0) f += l.n;
      const i0 = Math.floor(f), i1 = (i0 + 1) % (l.n + 1);
      const t = f - i0;
      const o0 = i0 * 3, o1 = i1 * 3;
      positions[p * 3] = l.arr[o0] + (l.arr[o1] - l.arr[o0]) * t;
      positions[p * 3 + 1] = l.arr[o0 + 1] + (l.arr[o1 + 1] - l.arr[o0 + 1]) * t;
      positions[p * 3 + 2] = l.arr[o0 + 2] + (l.arr[o1 + 2] - l.arr[o0 + 2]) * t;
    }
    points.geometry.attributes.position.needsUpdate = true;
  }

  let speedScale = 1;
  ctx.registerUpdate((dt) => {
    if (!points || !group.visible) return;
    for (let p = 0; p < count; p++) pIdx[p] += pSpeed[p] * dt * speedScale;
    writePositions();
  });

  rebuild();

  return {
    group,
    setEnabled(on) { group.visible = on; if (on && !points) rebuild(); },
    isEnabled() { return group.visible && tier !== 'off'; },
    setDensity(t) { tier = (t in TIERS) ? t : 'med'; rebuild(); },
    getDensity() { return tier; },
    setSpeedScale(s) { speedScale = s; },
  };
}
