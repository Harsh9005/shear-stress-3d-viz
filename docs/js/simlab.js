// simlab.js — focused "simulation lab": zoom into one region and watch the high-resolution flow,
// with a live Canvas2D cross-section showing the parabolic velocity profile + margination skew.
// All of this is illustrative idealized flow, NOT a validated CFD solve (labeled in the overlay).
import * as THREE from 'three';

function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

export function createSimLab(ctx, data, vessels, flow, tumors) {
  const stenosis = data.scenarios.find((s) => s.id === 'stenosis');
  const fixedTargets = [];
  (stenosis ? stenosis.hotspots : []).forEach((h, i) =>
    fixedTargets.push({ id: 'sten' + i, label: 'Stenosis ' + (i + 1), pos: h.pos, regime: 'extreme', wssText: '>1000 dyne/cm²', disturbed: true }));
  // The anatomical landmarks come from the data layer. They used to be three coordinate triples
  // written here, which put them outside the single source of truth and left them pointing at
  // empty space as soon as a vessel path changed.
  for (const t of (data.labTargets || [])) fixedTargets.push({ ...t });

  function targets() {
    const t = fixedTargets.slice();
    if (tumors) for (const id of tumors.active()) {
      const s = tumors.sites.find((x) => x.id === id);
      if (s) t.push({ id: 'tumor_' + id, label: s.label + ' tumor', pos: s.pos, regime: 'low_oscillatory', wssText: 'low & oscillatory', disturbed: true });
    }
    return t;
  }

  // DOM overlay
  const stage = document.createElement('div'); stage.id = 'simlab-stage'; stage.hidden = true;
  stage.innerHTML = `
    <div class="sl-card">
      <div class="sl-head"><span class="sl-title"></span><button class="sl-exit" aria-label="Exit lab">Exit</button></div>
      <canvas class="sl-canvas" width="240" height="240"></canvas>
      <div class="sl-readout"></div>
      <p class="sl-caption">Idealized illustrative flow — parabolic profile + shear-driven margination. Schematic, not a validated CFD simulation.</p>
    </div>`;
  document.body.appendChild(stage);
  const canvas = stage.querySelector('.sl-canvas');
  const g = canvas.getContext('2d');
  stage.querySelector('.sl-exit').addEventListener('click', () => exit());

  let active = false, cur = null, camTween = null, savedCam = null, savedTgt = null, savedFlow = null, animT = 0;

  // illustrative cross-section particles (radial fraction + angle)
  const PN = 90;
  const pr = new Float32Array(PN), pa = new Float32Array(PN), psp = new Float32Array(PN);
  function seedParticles() { for (let i = 0; i < PN; i++) { pr[i] = Math.sqrt(Math.random()); pa[i] = Math.random() * Math.PI * 2; psp[i] = 0.3 + Math.random(); } }

  function frameFor(p) { const v = new THREE.Vector3(p[0], p[1], p[2]); return { pos: v.clone().add(new THREE.Vector3(11, -15, 6)), target: v }; }

  function enter(targetId) {
    const t = targets().find((x) => x.id === targetId) || targets()[0];
    if (!t) return;
    if (!ctx.takeCamera('simlab')) return; // journey holds the camera
    active = true; cur = t; seedParticles(); animT = 0;
    savedCam = ctx.camera.position.clone(); savedTgt = ctx.controls.target.clone();
    savedFlow = { enabled: flow.isEnabled(), density: flow.getDensity() };
    ctx.controls.enabled = false;
    flow.setDensity('high'); flow.setEnabled(true); flow.setSpeedScale(0.35);
    if (!ctx.reducedMotion) { const f = frameFor(t.pos); camTween = { fromP: ctx.camera.position.clone(), toP: f.pos, fromT: ctx.controls.target.clone(), toT: f.target, t: 0 }; }
    else { const f = frameFor(t.pos); ctx.camera.position.copy(f.pos); ctx.controls.target.copy(f.target); }
    document.body.classList.add('simlab-active');
    stage.querySelector('.sl-title').textContent = t.label;
    stage.querySelector('.sl-readout').innerHTML = `<span class="sl-wss">${t.wssText}</span><span class="sl-regime regime-${t.regime}">${t.disturbed ? 'schematic disturbed flow' : 'laminar'}</span>`;
    stage.hidden = false;
    ctx.state.simlabTarget = t.id;
  }

  function exit() {
    if (!active) return;
    active = false; stage.hidden = true; document.body.classList.remove('simlab-active');
    ctx.controls.enabled = true; ctx.releaseCamera('simlab');
    flow.setSpeedScale(1); if (savedFlow) { flow.setDensity(savedFlow.density); flow.setEnabled(savedFlow.enabled); }
    if (savedCam) { ctx.camera.position.copy(savedCam); ctx.controls.target.copy(savedTgt); }
    ctx.state.simlabTarget = null; cur = null;
  }

  function draw() {
    const W = canvas.width, H = canvas.height, cx = W / 2, cy = H / 2, R = 92;
    g.clearRect(0, 0, W, H);
    // vessel wall
    g.strokeStyle = 'rgba(140,175,230,0.5)'; g.lineWidth = 2; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.stroke();
    // velocity profile (parabola across the horizontal diameter)
    g.strokeStyle = 'rgba(54,208,224,0.8)'; g.lineWidth = 2; g.beginPath();
    for (let i = 0; i <= 40; i++) { const u = i / 40, x = cx - R + u * 2 * R, rr = (u - 0.5) * 2, prof = 0.2 + 0.8 * (1 - rr * rr); const y = cy - prof * (R - 8); i ? g.lineTo(x, y) : g.moveTo(x, y); }
    g.stroke();
    g.fillStyle = 'rgba(147,164,189,0.8)'; g.font = '10px sans-serif'; g.fillText('velocity profile', cx - R, cy - R + 2);
    // particles (margination skew for low-shear / disturbed)
    const lowShear = cur && (cur.regime === 'low' || cur.regime === 'low_oscillatory' || cur.regime === 'extreme');
    const marg = cur && (cur.disturbed || cur.regime === 'low' || cur.regime === 'low_oscillatory') ? 0.5 : 0.05;
    for (let i = 0; i < PN; i++) {
      const rEff = Math.min(1, pr[i] + marg * (0.4 + 0.6 * Math.sin(animT * 0.6 + i)));
      const swirl = cur && cur.disturbed ? Math.sin(animT * 2 + i) * 0.15 : 0;
      const ang = pa[i] + swirl;
      const x = cx + Math.cos(ang) * rEff * (R - 6), y = cy + Math.sin(ang) * rEff * (R - 6);
      const stop = lowShear ? 0.18 : 0.6;
      g.fillStyle = lowShear ? 'rgba(120,200,240,0.9)' : 'rgba(255,180,90,0.9)';
      g.beginPath(); g.arc(x, y, 2, 0, Math.PI * 2); g.fill();
    }
    if (marg > 0.3) { g.fillStyle = 'rgba(255,206,74,0.9)'; g.font = '10px sans-serif'; g.fillText('margination → wall', cx - 30, cy + R - 4); }
  }

  ctx.registerUpdate((dt) => {
    if (!active) return;
    animT += dt;
    if (camTween) { camTween.t += dt / 1.4; const e = easeInOut(Math.min(camTween.t, 1)); ctx.camera.position.lerpVectors(camTween.fromP, camTween.toP, e); ctx.controls.target.lerpVectors(camTween.fromT, camTween.toT, e); if (camTween.t >= 1) camTween = null; }
    draw();
  });

  return { enter, exit, isActive: () => active, targets };
}
