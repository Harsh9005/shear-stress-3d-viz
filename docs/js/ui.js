// ui.js — sidebars, scenario selector, layer toggles, hover/tap tooltips (debounced raycast), help.
import * as THREE from 'three';

export function buildUI(ctx, data, mods) {
  const { vessels, flow, panels, scenarios, journey } = mods;
  const left = document.getElementById('panel-left');
  const right = document.getElementById('panel-right');

  // ── Right panel: quantitative panels ──
  if (panels) { right.append(panels.el); panels.flashGap(); }

  // ── Left panel: scenarios + layers ──
  const scSec = document.createElement('section');
  scSec.className = 'section';
  scSec.innerHTML = '<h2>Scenario</h2>';
  const radgroup = document.createElement('div');
  radgroup.className = 'scenarios'; radgroup.setAttribute('role', 'radiogroup'); radgroup.setAttribute('aria-label', 'Pathology scenario');
  const sByID = Object.fromEntries(data.scenarios.map((s) => [s.id, s]));
  let activeBtn = null;
  for (const s of (scenarios ? scenarios.list : [])) {
    const b = document.createElement('button');
    b.className = 'scenario-btn'; b.textContent = s.label;
    b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', s.id === 'healthy' ? 'true' : 'false');
    if (s.id === 'healthy') { b.classList.add('active'); activeBtn = b; }
    b.addEventListener('click', () => {
      if (activeBtn) { activeBtn.classList.remove('active'); activeBtn.setAttribute('aria-checked', 'false'); }
      activeBtn = b; b.classList.add('active'); b.setAttribute('aria-checked', 'true');
      scenarios.apply(s.id);
      const scn = sByID[s.id];
      if (panels) { if (s.id === 'healthy') panels.showSystem(); else panels.showScenario(scn); }
    });
    radgroup.append(b);
  }
  scSec.append(radgroup);

  const lySec = document.createElement('section');
  lySec.className = 'section';
  lySec.innerHTML = '<h2>Layers</h2>';
  // flow toggle
  const flowRow = toggleRow('Flow particles', flow ? flow.isEnabled() : false, (on) => flow && flow.setEnabled(on));
  // density
  const densRow = document.createElement('label'); densRow.className = 'ctl-row';
  densRow.innerHTML = '<span>Particle density</span>';
  const dsel = document.createElement('select'); dsel.className = 'ctl-select';
  for (const d of ['low', 'med', 'high']) { const o = document.createElement('option'); o.value = d; o.textContent = d[0].toUpperCase() + d.slice(1); dsel.append(o); }
  dsel.value = flow ? flow.getDensity() === 'off' ? 'med' : flow.getDensity() : 'med';
  dsel.addEventListener('change', () => { if (flow) { flow.setDensity(dsel.value); flow.setEnabled(true); flowRow.input.checked = true; } });
  densRow.append(dsel);
  // colourblind
  const cbRow = toggleRow('Colour-blind palette', false, (on) => {
    ctx.colorscale.setColorblind(on); ctx.state.colorblind = on;
    vessels && vessels.recomputeColors();
    panels && panels.refreshPalette();
    flow && flow.setDensity(flow.getDensity());
    scenarios && scenarios.apply(ctx.state.activeScenarioId);
  });
  lySec.append(flowRow.el, densRow, cbRow.el);

  left.append(scSec, lySec);

  // ── Journey button ──
  const jbtn = document.getElementById('journey-btn');
  if (jbtn && journey) jbtn.addEventListener('click', () => journey.start());

  // ── Help / about ──
  const helpBtn = document.getElementById('help-btn');
  const modal = document.getElementById('about-modal');
  if (helpBtn && modal) {
    modal.innerHTML = `<div class="modal-card">
      <button class="modal-close" aria-label="Close">×</button>
      <h2>About</h2>
      <p>An interactive map of <b>wall shear stress (WSS)</b> across the human circulatory system —
      the mechanical force flowing blood exerts on vessel walls. WSS spans four orders of magnitude,
      from near-stagnant hepatic sinusoids (~0.1 dyne/cm²) to stenotic hotspots (&gt;1000 dyne/cm²).</p>
      <p>A circulating nanocarrier must survive this entire range. Use the <b>scenarios</b> to see how
      disease reshapes the landscape, launch the <b>nanoparticle journey</b> to follow a carrier through
      it, and read <b>The Shear Gap</b> to see why benchtop tests — run in near-still fluid — miss these forces.</p>
      <p class="modal-foot">WSS magnitudes are representative values consistent with the hemodynamics and
      nanomedicine literature.</p>
    </div>`;
    const close = () => { modal.hidden = true; };
    helpBtn.addEventListener('click', () => { modal.hidden = false; });
    modal.addEventListener('click', (e) => { if (e.target === modal || e.target.classList.contains('modal-close')) close(); });
    window.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  }

  // ── Hover / tap tooltips via debounced raycast ──
  const ray = new THREE.Raycaster();
  const ptr = new THREE.Vector2();
  const tip = document.getElementById('tooltip');
  let pending = false, lastEv = null, sticky = false;

  function schedule(e) { lastEv = e; if (!pending) { pending = true; requestAnimationFrame(pick); } }

  function pick() {
    pending = false;
    if (!lastEv || (journey && journey.isActive())) return;
    const r = ctx.renderer.domElement.getBoundingClientRect();
    ptr.x = ((lastEv.clientX - r.left) / r.width) * 2 - 1;
    ptr.y = -((lastEv.clientY - r.top) / r.height) * 2 + 1;
    ray.setFromCamera(ptr, ctx.camera);
    const hits = ray.intersectObjects(vessels ? vessels.pickables : [], false);
    if (hits.length) showTip(hits[0].object.userData, lastEv);
    else if (!sticky) hideTip();
  }

  function showTip(u, ev) {
    if (u.kind === 'vessel') {
      tip.innerHTML = `<b>${u.name}</b><span class="tip-wss">${u.wss[0]} – ${u.wss[1]} dyne/cm²</span><span class="tip-note">${u.note}</span>`;
      vessels.highlight(u.id);
      panels && panels.showVessel(u);
    } else if (u.kind === 'organ') {
      tip.innerHTML = `<b>${u.name}</b><span class="tip-note">${u.note}</span>`;
      vessels.highlight(null);
    } else return;
    tip.hidden = false;
    const pad = 14, tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + tw > window.innerWidth - 8) x = ev.clientX - tw - pad;
    if (y + th > window.innerHeight - 8) y = ev.clientY - th - pad;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }

  function hideTip() { tip.hidden = true; vessels && vessels.highlight(null); if (panels && !sticky) panels.showSystem(); }

  const canvas = ctx.renderer.domElement;
  if (ctx.coarsePointer) {
    // tap-to-select (sticky) on touch
    canvas.addEventListener('pointerdown', (e) => { sticky = false; schedule(e); sticky = true; });
    document.addEventListener('pointerdown', (e) => { if (e.target === canvas) return; sticky = false; hideTip(); });
  } else {
    canvas.addEventListener('pointermove', schedule);
    canvas.addEventListener('pointerleave', hideTip);
  }
}

function toggleRow(label, checked, onChange) {
  const el = document.createElement('label'); el.className = 'ctl-row';
  const span = document.createElement('span'); span.textContent = label;
  const input = document.createElement('input'); input.type = 'checkbox'; input.className = 'ctl-toggle'; input.checked = checked;
  input.addEventListener('change', () => onChange(input.checked));
  el.append(span, input);
  return { el, input };
}
