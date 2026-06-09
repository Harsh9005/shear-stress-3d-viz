// panels.js — the quantitative "intelligent" layer: WSS spectrum, the Shear Gap chart, live readout.
// Pure DOM/Canvas (no heavy deps) so it doubles as the no-WebGL fallback.

function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
}

export function buildPanels(data, colorscale) {
  const logMin = data.meta.logMin, logMax = data.meta.logMax;
  const logPos = (v) => Math.max(0, Math.min(1, (Math.log10(Math.max(0.05, v)) - logMin) / (logMax - logMin)));

  // ── WSS spectrum ──
  const spectrum = el('section', 'panel');
  spectrum.append(el('h2', 'panel-h', 'Wall shear stress <span class="unit">dyne/cm²</span>'));
  const bar = el('div', 'spectrum-bar');
  bar.style.background = colorscale.gradientCSS();
  const ticks = el('div', 'spectrum-ticks');
  for (const w of [0.1, 1, 10, 100, 1000]) {
    const t = el('span', 'tick'); t.style.left = (logPos(w) * 100) + '%';
    t.innerHTML = `<i></i><b>${w}</b>`;
    ticks.append(t);
  }
  const cursor = el('span', 'spectrum-cursor'); cursor.hidden = true; bar.append(cursor);
  spectrum.append(bar, ticks);
  const regions = el('p', 'spectrum-note', 'Four orders of magnitude — from near-stagnant hepatic sinusoids to stenotic hotspots.');
  spectrum.append(regions);

  // ── The Shear Gap ──
  const gap = el('section', 'panel gap-panel');
  gap.append(el('h2', 'panel-h', 'The Shear Gap <span class="sub">why benchtop tests mislead</span>'));
  const gapChart = el('div', 'gap-chart');
  const gapRows = [];
  for (const g of data.panels.shearGap) {
    const row = el('div', 'gap-row' + (g.kind === 'physiological' ? ' physiological' : ''));
    row.append(el('span', 'gap-label', g.method));
    const track = el('div', 'gap-track');
    const fill = el('div', 'gap-fill');
    fill.dataset.w = (logPos(g.shear) * 100).toFixed(1);
    fill.style.width = '0%';
    track.append(fill);
    const val = el('span', 'gap-val', g.openEnded ? `&gt;${g.shear}` : String(g.shear));
    row.append(track, val);
    gapChart.append(row);
    gapRows.push(fill);
  }
  gap.append(gapChart, el('p', 'gap-take', data.panels.shearGapTakeaway));

  // ── Readout card ──
  const readout = el('section', 'panel readout');
  const SYSTEM_SUMMARY = {
    title: 'The whole system', wssText: '0.1 – &gt;1000 dyne/cm²', regime: 'four orders of magnitude',
    note: 'Hover a vessel for its local shear, or pick a scenario to see how disease reshapes the landscape.',
  };
  function renderReadout(info) {
    readout.innerHTML = '';
    readout.append(el('h2', 'panel-h', info.title));
    const wss = el('div', 'readout-wss');
    wss.innerHTML = `<span class="readout-num">${info.wssText}</span>`;
    readout.append(wss);
    if (info.regime) readout.append(el('div', 'readout-regime regime-' + (info.regimeKey || 'na'), info.regime));
    if (info.note) readout.append(el('p', 'readout-note', info.note));
  }
  renderReadout(SYSTEM_SUMMARY);

  function flashGap() {
    requestAnimationFrame(() => gapRows.forEach((f, i) => {
      setTimeout(() => { f.style.width = f.dataset.w + '%'; }, 120 + i * 110);
    }));
  }

  const container = el('div', 'panels');
  container.append(spectrum, gap, readout);

  const REGIME_LABEL = {
    extreme: 'near-stagnant', low: 'low shear', moderate: 'moderate shear', high: 'high shear',
    low_oscillatory: 'low & oscillatory',
  };

  return {
    el: container,
    flashGap,
    refreshPalette() { bar.style.background = colorscale.gradientCSS(); },
    showVessel(u) {
      cursor.hidden = false;
      const m = (u.wss[0] + u.wss[1]) / 2;
      cursor.style.left = (logPos(m) * 100) + '%';
      renderReadout({
        title: u.name,
        wssText: `${u.wss[0]} – ${u.wss[1]} dyne/cm²`,
        regime: REGIME_LABEL[u.regime] || u.regime, regimeKey: u.regime,
        note: u.note,
      });
    },
    showSystem() { cursor.hidden = true; renderReadout(SYSTEM_SUMMARY); },
    showScenario(s) {
      cursor.hidden = true;
      renderReadout({ title: s.label, wssText: '', regime: '', note: s.blurb });
    },
    mountFallback(host) {
      host.append(spectrum.cloneNode(true), gap.cloneNode(true));
      // animate the cloned gap bars too
      host.querySelectorAll('.gap-fill').forEach((f, i) => setTimeout(() => { f.style.width = f.dataset.w + '%'; }, 200 + i * 110));
    },
  };
}
