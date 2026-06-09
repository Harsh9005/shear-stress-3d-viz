// scenarios.js — switches between the healthy baseline and pathologies: animated WSS recolour,
// hotspot ignition, dimming of unaffected vessels, and a camera framing nudge for the worst case.
import * as THREE from 'three';

function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

export function createScenarioController(ctx, data, vessels) {
  const byId = Object.fromEntries(data.scenarios.map((s) => [s.id, s]));
  let onChange = null;
  let current = data.scenarios[0];

  let tweens = [];
  let tweenT = 1, animating = false;
  let camTween = null;

  function targetColor(change) {
    if (change.sentinel) return ctx.colorscale.colorAt(change.sentinel);
    const [lo, hi] = change.displayWss;
    return ctx.colorscale.colorAt((lo + hi) / 2);
  }

  function apply(id) {
    const s = byId[id];
    if (!s || !vessels) return;
    const affected = new Set();
    const colorByVessel = new Map();
    for (const ch of s.changes) {
      const col = targetColor(ch);
      for (const vid of ch.vessels) { affected.add(vid); colorByVessel.set(vid, col); }
    }
    tweens = [];
    for (const it of vessels.items.values()) {
      const to = colorByVessel.get(it.vessel.id) || it.baseColor;
      const dimTo = (s.dim && id !== 'healthy' && !affected.has(it.vessel.id)) ? 0.3 : 1.0;
      tweens.push({
        u: it.mat.uniforms,
        from: it.mat.uniforms.uColor.value.clone(), to: to.clone(),
        dimFrom: it.mat.uniforms.uDim.value, dimTo,
      });
    }
    tweenT = 0; animating = true;

    vessels.showHotspots(s.hotspots);
    vessels.setScenarioBeds(s.beds);

    // Camera framing nudge for the combined worst case.
    if (s.hotspots && s.hotspots.length && (id === 'combined' || id === 'stenosis')) {
      const c = new THREE.Vector3();
      for (const h of s.hotspots) c.add(new THREE.Vector3(h.pos[0], h.pos[1], h.pos[2]));
      c.multiplyScalar(1 / s.hotspots.length);
      camTween = { from: ctx.controls.target.clone(), to: ctx.controls.target.clone().lerp(c, 0.45), t: 0 };
    }

    ctx.state.activeScenarioId = id;
    current = s;
    if (onChange) onChange(s);
  }

  ctx.registerUpdate((dt) => {
    if (animating) {
      tweenT += dt / 0.6;
      const e = easeInOut(Math.min(tweenT, 1));
      for (const tw of tweens) {
        tw.u.uColor.value.lerpColors(tw.from, tw.to, e);
        tw.u.uDim.value = tw.dimFrom + (tw.dimTo - tw.dimFrom) * e;
      }
      if (tweenT >= 1) animating = false;
    }
    if (camTween) {
      camTween.t += dt / 0.6;
      const e = easeInOut(Math.min(camTween.t, 1));
      ctx.controls.target.lerpVectors(camTween.from, camTween.to, e);
      if (camTween.t >= 1) camTween = null;
    }
  });

  return {
    list: data.scenarios.map((s) => ({ id: s.id, label: s.label })),
    apply,
    current: () => current,
    set onChange(fn) { onChange = fn; },
  };
}
