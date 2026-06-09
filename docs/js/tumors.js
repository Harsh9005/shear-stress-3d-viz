// tumors.js — combinable multi-site tumor layer. Owns its OWN bed/hotspot visuals and marks
// nearVessels as disturbed for the flow field. It NEVER writes vessel colour directly — it exposes
// affectedVessels() and asks scenarios.js (the single colour writer) to recompose.
import * as THREE from 'three';
import { buildBed } from './vessels.js';

function glowTex() {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.3, 'rgba(230,150,255,0.8)');
  grad.addColorStop(1, 'rgba(180,60,230,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
  const t = new THREE.Texture(c); t.needsUpdate = true; return t;
}

function hashSeed(id) { let h = 2166136261; for (let i = 0; i < id.length; i++) { h ^= id.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0) % 100000; }

export function createTumors(ctx, data, vessels, flow, scenarios) {
  const sites = Object.fromEntries(data.tumorSites.map((s) => [s.id, s]));
  const active = new Set();
  const bedGroup = new THREE.Group(); ctx.scene.add(bedGroup);
  const hotspotGroup = new THREE.Group(); ctx.scene.add(hotspotGroup);
  const tex = glowTex();
  const sprites = [];

  function affectedVessels() {
    const set = new Set();
    for (const id of active) for (const v of sites[id].nearVessels) set.add(v);
    return set;
  }

  function rebuild() {
    while (bedGroup.children.length) bedGroup.remove(bedGroup.children[0]);
    while (hotspotGroup.children.length) hotspotGroup.remove(hotspotGroup.children[0]);
    sprites.length = 0;
    for (const id of active) {
      const s = sites[id];
      bedGroup.add(buildBed(ctx, { center: s.pos, spread: s.spread }, s.representativeWss, hashSeed(id)));
      const smat = new THREE.SpriteMaterial({ map: tex, color: new THREE.Color(0.85, 0.3, 0.9), transparent: true, opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending });
      const sp = new THREE.Sprite(smat); sp.position.set(s.pos[0], s.pos[1], s.pos[2]); sp.scale.setScalar(6);
      hotspotGroup.add(sp); sprites.push(sp);
    }
    if (flow) flow.setDisturbedVessels('tumor', affectedVessels());
  }

  ctx.registerUpdate((dt, t) => {
    for (let i = 0; i < sprites.length; i++) {
      sprites[i].material.opacity = 0.7 + Math.sin(t * 2.5 + i) * 0.25;
      const b = sprites[i].userData.base || (sprites[i].userData.base = sprites[i].scale.x);
      sprites[i].scale.setScalar(b * (1 + Math.sin(t * 2.5 + i) * 0.12));
    }
  });

  return {
    sites: data.tumorSites,
    toggle(id) {
      if (!sites[id]) return false;
      if (active.has(id)) active.delete(id); else active.add(id);
      rebuild();
      if (scenarios) scenarios.reapply();
      ctx.state.activeTumors = [...active];
      return active.has(id);
    },
    active: () => active,
    affectedVessels,
    note: (id) => sites[id] && sites[id].note,
    clearAll() { active.clear(); rebuild(); if (scenarios) scenarios.reapply(); ctx.state.activeTumors = []; },
  };
}
