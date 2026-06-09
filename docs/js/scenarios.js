// scenarios.js — single writer of vessel colour. Composes base → scenario → tumor overlay so
// tumors.js never touches uColor directly (avoids the two racing over vessel colour).
import * as THREE from 'three';

function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

export function createScenarioController(ctx, data, vessels) {
  const byId = Object.fromEntries(data.scenarios.map((s) => [s.id, s]));
  let onChange = null;
  let current = data.scenarios[0];
  let tumors = null; // set via setTumors (queried during composition)

  let tweens = [];
  let tweenT = 1, animating = false;
  let camTween = null;

  function targetColor(change) {
    if (change.sentinel) return ctx.colorscale.colorAt(change.sentinel);
    const [lo, hi] = change.displayWss;
    return ctx.colorscale.colorAt((lo + hi) / 2);
  }

  // Compose colour + precedence per vessel: scenario changes (extreme=3 wins) then tumor overlay (low=2).
  function compose(s) {
    const map = new Map(); // vesselId → { color, prec }
    const setIfHigher = (vid, color, prec) => {
      const e = map.get(vid);
      if (!e || prec > e.prec) map.set(vid, { color, prec });
    };
    for (const ch of s.changes) {
      const col = targetColor(ch);
      const prec = ch.regime === 'extreme' ? 3 : 2;
      for (const vid of ch.vessels) setIfHigher(vid, col, prec);
    }
    if (tumors) {
      const tcol = ctx.colorscale.colorAt(1.0); // low_oscillatory representative
      for (const vid of tumors.affectedVessels()) setIfHigher(vid, tcol, 2);
    }
    return map;
  }

  function startTweens(s) {
    const map = compose(s);
    const affected = map; // keys = affected vessels
    tweens = [];
    for (const it of vessels.items.values()) {
      const target = affected.get(it.vessel.id);
      const to = target ? target.color : it.baseColor;
      const dimTo = (s.dim && s.id !== 'healthy' && !affected.has(it.vessel.id)) ? 0.3 : 1.0;
      tweens.push({
        u: it.mat.uniforms,
        from: it.mat.uniforms.uColor.value.clone(), to: to.clone(),
        dimFrom: it.mat.uniforms.uDim.value, dimTo,
      });
    }
    tweenT = 0; animating = true;
  }

  function apply(id) {
    const s = byId[id];
    if (!s || !vessels) return;
    startTweens(s);
    vessels.showHotspots(s.hotspots);
    vessels.setScenarioBeds(s.beds);
    if (s.hotspots && s.hotspots.length && (id === 'combined' || id === 'stenosis') && ctx.takeCamera('scenario-nudge') !== false) {
      // (scenario nudge is non-exclusive; release immediately, it only sets a target tween)
      const c = new THREE.Vector3();
      for (const h of s.hotspots) c.add(new THREE.Vector3(h.pos[0], h.pos[1], h.pos[2]));
      c.multiplyScalar(1 / s.hotspots.length);
      camTween = { from: ctx.controls.target.clone(), to: ctx.controls.target.clone().lerp(c, 0.45), t: 0 };
      ctx.releaseCamera('scenario-nudge');
    }
    ctx.state.activeScenarioId = id;
    current = s;
    if (onChange) onChange(s);
  }

  // Re-run composition for the CURRENT scenario (e.g. after a tumor toggles or colourblind changes).
  function reapply() { if (vessels) startTweens(current); }

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
    reapply,
    current: () => current,
    setTumors(t) { tumors = t; },
    set onChange(fn) { onChange = fn; },
  };
}
