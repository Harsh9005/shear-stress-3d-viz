// colorscale.js — the SOLE owner of the WSS log-colour mapping.
// Both the 3D vessels and every legend/panel derive colour from here, so they can never drift.
import * as THREE from 'three';

// Colourblind-safe alternative ramp (cividis: perceptually ordered, CVD-robust).
const CIVIDIS = [
  { stop: 0.0,  rgb: [0, 32, 76] },
  { stop: 0.25, rgb: [45, 76, 110] },
  { stop: 0.5,  rgb: [124, 123, 120] },
  { stop: 0.75, rgb: [187, 177, 110] },
  { stop: 1.0,  rgb: [255, 233, 69] },
];

function lerp(a, b, t) { return a + (b - a) * t; }

function sampleRamp(ramp, stop) {
  const s = Math.max(0, Math.min(1, stop));
  for (let i = 0; i < ramp.length - 1; i++) {
    const a = ramp[i], b = ramp[i + 1];
    if (s >= a.stop && s <= b.stop) {
      const t = (s - a.stop) / (b.stop - a.stop || 1);
      return [
        Math.round(lerp(a.rgb[0], b.rgb[0], t)),
        Math.round(lerp(a.rgb[1], b.rgb[1], t)),
        Math.round(lerp(a.rgb[2], b.rgb[2], t)),
      ];
    }
  }
  return ramp[ramp.length - 1].rgb.slice();
}

export function createColorScale(data) {
  const heat = data.colorscale.map((c) => ({ stop: c.stop, wss: c.wss, rgb: c.rgb }));
  const logMin = data.meta.logMin;
  const logMax = data.meta.logMax;
  let colorblind = false;

  // Map a WSS value (dyne/cm²) to a stop in [0,1] on the shared log scale.
  function wssToStop(wss) {
    const w = Math.max(0.05, wss);
    return Math.max(0, Math.min(1, (Math.log10(w) - logMin) / (logMax - logMin)));
  }

  function rgbAt(wss) {
    const stop = wssToStop(wss);
    return colorblind ? sampleRamp(CIVIDIS, stop) : sampleRamp(heat, stop);
  }

  function rgbAtStop(stop) {
    return colorblind ? sampleRamp(CIVIDIS, stop) : sampleRamp(heat, stop);
  }

  // THREE.Color for the 3D side of the scale.
  //
  // The colour space MUST be declared. The ramp stops are sRGB bytes — the same numbers
  // gradientCSS() hands the browser — but THREE.Color's numeric constructor assigns straight
  // into the working space, which ColorManagement makes linear-sRGB. Without the third argument
  // an sRGB value is stored as though it were already linear, and the vessel then renders a
  // different colour from the legend swatch that claims to describe it.
  function colorAt(wss) {
    const [r, g, b] = rgbAt(wss);
    return new THREE.Color().setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace);
  }

  // CSS gradient string (left=low WSS, right=high) for legends/panels.
  function gradientCSS() {
    const ramp = colorblind ? CIVIDIS : heat;
    const stops = ramp.map((c) => `rgb(${c.rgb.join(',')}) ${(c.stop * 100).toFixed(1)}%`);
    return `linear-gradient(90deg, ${stops.join(', ')})`;
  }

  return {
    wssToStop,
    rgbAt,
    rgbAtStop,
    colorAt,
    gradientCSS,
    get logMin() { return logMin; },
    get logMax() { return logMax; },
    get colorblind() { return colorblind; },
    setColorblind(v) { colorblind = !!v; },
    get stops() { return heat; },
  };
}
