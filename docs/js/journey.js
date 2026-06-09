// journey.js — a guided fly-through following a ~100 nm carrier; an integrity gauge reacts to the
// real shear forces at each waypoint, climaxing in burst rupture at the >1000 dyne/cm² stenosis.
import * as THREE from 'three';

function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

export function createJourney(ctx, data, vessels, flow) {
  const J = data.journey;
  const wps = J.waypoints;
  const cs = ctx.colorscale;

  // cumulative integrity after each waypoint
  const cumulative = [];
  let acc = 100;
  for (const wp of wps) { acc += wp.integrityDelta || 0; cumulative.push(Math.max(0, acc)); }

  // resolve waypoint world positions
  const posOf = wps.map((wp) => {
    if (wp.pos) return new THREE.Vector3(wp.pos[0], wp.pos[1], wp.pos[2]);
    const v = data.vessels.find((x) => x.id === wp.vesselId);
    const curve = new THREE.CatmullRomCurve3(v.path.map((p) => new THREE.Vector3(p[0], p[1], p[2])), false, 'centripetal');
    return curve.getPointAt(Math.max(0, Math.min(1, wp.tAlong ?? 0.5)));
  });

  // NP sprite
  const npTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d');
    const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.4, 'rgba(180,230,255,0.9)'); grd.addColorStop(1, 'rgba(120,180,255,0)');
    g.fillStyle = grd; g.fillRect(0, 0, 64, 64); const t = new THREE.Texture(c); t.needsUpdate = true; return t;
  })();
  const np = new THREE.Sprite(new THREE.SpriteMaterial({ map: npTex, transparent: true, depthTest: false, blending: THREE.AdditiveBlending }));
  np.scale.setScalar(3.2); np.visible = false; np.renderOrder = 10; ctx.scene.add(np);

  // fragment burst (for the rupture climax)
  const fragGeo = new THREE.BufferGeometry();
  const FRAG = 40; const fragPos = new Float32Array(FRAG * 3); const fragVel = [];
  for (let i = 0; i < FRAG; i++) fragVel.push(new THREE.Vector3());
  fragGeo.setAttribute('position', new THREE.BufferAttribute(fragPos, 3));
  const frag = new THREE.Points(fragGeo, new THREE.PointsMaterial({ color: 0xfff0d0, size: 1.2, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
  frag.visible = false; ctx.scene.add(frag);
  let fragT = 0, fragging = false;

  // DOM stage
  const stage = document.getElementById('journey-stage');

  let active = false, idx = -1, playing = false, dwell = 0;
  let camTween = null, npTween = null;
  let savedCam = null, savedTarget = null;

  function frameFor(p) {
    return { pos: p.clone().add(new THREE.Vector3(16, -22, 9)), target: p.clone() };
  }

  function renderStage() {
    if (idx >= wps.length) { renderResolution(); return; }
    const wp = wps[idx];
    const integ = cumulative[idx];
    const stop = cs.wssToStop(wp.shearDyne);
    const shearText = wp.openEnded ? `&gt;${wp.shearDyne}` : `${wp.shearDyne}`;
    const ruptured = !!wp.climax;
    stage.innerHTML = `
      <div class="jcard ${ruptured ? 'climax' : ''}">
        <div class="jhead">
          <span class="jstep">${idx + 1} / ${wps.length}</span>
          <span class="jevent ${ruptured ? 'rupture' : ''}">${wp.event}</span>
        </div>
        <h3>${wp.title}</h3>
        <div class="jshear">
          <div class="jshear-bar" style="background:${cs.gradientCSS()}">
            <span class="jshear-mark" style="left:${(stop * 100).toFixed(1)}%"></span>
          </div>
          <div class="jshear-val">${shearText} <span class="unit">dyne/cm²</span></div>
        </div>
        <p class="jcopy">${wp.copy}</p>
        ${wp.shearRateNote ? `<p class="jnote">— ${wp.shearRateNote}</p>` : ''}
        <div class="jgauge">
          <span class="jgauge-label">Carrier integrity</span>
          <div class="jgauge-track"><div class="jgauge-fill ${integ < 30 ? 'crit' : integ < 70 ? 'warn' : 'ok'}" style="width:${integ}%"></div></div>
          <span class="jgauge-pct">${Math.round(integ)}%</span>
        </div>
        <div class="jctrls">
          <button class="jbtn" data-act="prev" ${idx === 0 ? 'disabled' : ''}>‹ Back</button>
          <button class="jbtn" data-act="play">${playing ? '❚❚ Pause' : '▶ Play'}</button>
          <button class="jbtn" data-act="next">${idx === wps.length - 1 ? 'Result ›' : 'Next ›'}</button>
          <button class="jbtn jexit" data-act="exit">Exit</button>
        </div>
      </div>`;
    wire();
    ctx.state.integrityPct = Math.round(integ);
  }

  function renderResolution() {
    const integ = cumulative[cumulative.length - 1];
    stage.innerHTML = `
      <div class="jcard resolution">
        <div class="jhead"><span class="jevent rupture">Outcome</span></div>
        <h3>${J.resolution.title}</h3>
        <div class="jgauge">
          <span class="jgauge-label">Carrier integrity at target</span>
          <div class="jgauge-track"><div class="jgauge-fill crit" style="width:${integ}%"></div></div>
          <span class="jgauge-pct">${Math.round(integ)}%</span>
        </div>
        <p class="jcopy">${J.resolution.copy}</p>
        <div class="jctrls">
          <button class="jbtn" data-act="replay">↻ Replay</button>
          <button class="jbtn jexit" data-act="exit">Done</button>
        </div>
      </div>`;
    wire();
    ctx.state.integrityPct = Math.round(integ);
  }

  function wire() {
    stage.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', () => {
      const a = b.dataset.act;
      if (a === 'next') goTo(idx + 1);
      else if (a === 'prev') goTo(idx - 1);
      else if (a === 'play') { playing = !playing; dwell = 0; renderStage(); }
      else if (a === 'exit') stop();
      else if (a === 'replay') goTo(0, true);
    }));
  }

  function goTo(i, restart) {
    if (i < 0) return;
    if (i > wps.length) i = wps.length;
    const prevPos = idx >= 0 && idx < wps.length ? posOf[idx] : posOf[0];
    idx = i;
    if (idx >= wps.length) { renderResolution(); playing = false; return; }
    const target = posOf[idx];
    // move NP + camera
    if (ctx.reducedMotion) {
      np.position.copy(target);
      const f = frameFor(target); ctx.camera.position.copy(f.pos); ctx.controls.target.copy(f.target);
    } else {
      npTween = { from: (restart ? target : prevPos).clone(), to: target.clone(), t: 0 };
      const f = frameFor(target);
      camTween = { fromP: ctx.camera.position.clone(), toP: f.pos, fromT: ctx.controls.target.clone(), toT: f.target, t: 0 };
    }
    if (wps[idx].climax) triggerRupture(target);
    renderStage();
  }

  function triggerRupture(at) {
    fragging = true; fragT = 0; frag.visible = true; frag.material.opacity = 1;
    for (let i = 0; i < FRAG; i++) {
      fragPos[i * 3] = at.x; fragPos[i * 3 + 1] = at.y; fragPos[i * 3 + 2] = at.z;
      fragVel[i].set(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5).normalize().multiplyScalar(8 + Math.random() * 10);
    }
    fragGeo.attributes.position.needsUpdate = true;
    np.material.color.setRGB(1, 0.5, 0.4);
    if (ctx.bloom) { const b = ctx.bloom; const o = b.strength; b.strength = 1.8; setTimeout(() => { b.strength = o; }, 450); }
  }

  ctx.registerUpdate((dt) => {
    if (!active) return;
    if (npTween) { npTween.t += dt / 1.6; const e = easeInOut(Math.min(npTween.t, 1)); np.position.lerpVectors(npTween.from, npTween.to, e); if (npTween.t >= 1) npTween = null; }
    if (camTween) {
      camTween.t += dt / 1.6; const e = easeInOut(Math.min(camTween.t, 1));
      ctx.camera.position.lerpVectors(camTween.fromP, camTween.toP, e);
      ctx.controls.target.lerpVectors(camTween.fromT, camTween.toT, e);
      if (camTween.t >= 1) camTween = null;
    }
    if (fragging) {
      fragT += dt;
      for (let i = 0; i < FRAG; i++) { fragPos[i * 3] += fragVel[i].x * dt; fragPos[i * 3 + 1] += fragVel[i].y * dt; fragPos[i * 3 + 2] += fragVel[i].z * dt; }
      frag.geometry.attributes.position.needsUpdate = true;
      frag.material.opacity = Math.max(0, 1 - fragT / 1.2);
      if (fragT > 1.2) { fragging = false; frag.visible = false; }
    }
    if (playing && !camTween && !npTween) {
      dwell += dt;
      if (dwell > 4) { dwell = 0; goTo(idx + 1); }
    }
  });

  function start() {
    if (active) return;
    if (ctx.takeCamera && !ctx.takeCamera('journey')) return; // sim-lab holds the camera
    active = true; playing = false; dwell = 0;
    savedCam = ctx.camera.position.clone(); savedTarget = ctx.controls.target.clone();
    ctx.controls.enabled = false;
    np.visible = true; np.material.color.setRGB(1, 1, 1);
    document.body.classList.add('journey-active');
    stage.hidden = false;
    goTo(0, true);
  }

  function stop() {
    active = false; playing = false; np.visible = false; frag.visible = false; fragging = false;
    ctx.controls.enabled = true;
    if (ctx.releaseCamera) ctx.releaseCamera('journey');
    document.body.classList.remove('journey-active');
    stage.hidden = true;
    if (savedCam) { ctx.camera.position.copy(savedCam); ctx.controls.target.copy(savedTarget); }
    ctx.state.integrityPct = 100;
  }

  return { start, stop, isActive: () => active };
}
