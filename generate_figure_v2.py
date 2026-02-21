#!/usr/bin/env python3
"""
Professional 2D Illustration — Wall Shear Stress in the Human Circulatory System
VERSION 2: Enhanced realism, 3D depth, and visual polish
==========================================================================

Improvements over v1:
- Wider vein/artery separation for visual clarity
- Smoother body silhouette with gradient-filled organs
- Stronger 3D tube effect with multi-layer glow + specular
- Finer branching capillary networks
- Better annotation placement
- Sharper WSS color differentiation
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.patches import FancyBboxPatch, Circle, Ellipse
from matplotlib.lines import Line2D
from matplotlib.colorbar import ColorbarBase
from scipy.interpolate import splprep, splev
import matplotlib.gridspec as gridspec
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIG
# =============================================================================
DPI = 300
FIG_W, FIG_H = 14, 20
BG = '#080c18'

# WSS colormap
_wss_pts = [
    (0.00, '#060840'),
    (0.10, '#0030aa'),
    (0.20, '#0088dd'),
    (0.30, '#00bbaa'),
    (0.42, '#22cc44'),
    (0.52, '#99dd00'),
    (0.62, '#eedd00'),
    (0.72, '#ff9900'),
    (0.82, '#ff3300'),
    (0.92, '#cc0055'),
    (1.00, '#9900cc'),
]

def _hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16)/255 for i in (0,2,4))

def make_cmap():
    cdict = {'red':[], 'green':[], 'blue':[]}
    for p, h in _wss_pts:
        r, g, b = _hex2rgb(h)
        cdict['red'].append((p, r, r))
        cdict['green'].append((p, g, g))
        cdict['blue'].append((p, b, b))
    return LinearSegmentedColormap('wss', cdict, N=512)

CMAP = make_cmap()
NORM = LogNorm(vmin=0.08, vmax=1500)

# =============================================================================
# CURVE UTILITIES
# =============================================================================
def smooth(pts, n=250, s=0.0):
    pts = np.array(pts, dtype=float)
    if len(pts) < 3:
        t = np.linspace(0, 1, n)
        return pts[0,0]+(pts[-1,0]-pts[0,0])*t, pts[0,1]+(pts[-1,1]-pts[0,1])*t
    try:
        tck, _ = splprep([pts[:,0], pts[:,1]], s=s, k=min(3, len(pts)-1))
        return splev(np.linspace(0, 1, n), tck)
    except:
        t = np.linspace(0, 1, n)
        return np.interp(t, np.linspace(0,1,len(pts)), pts[:,0]), \
               np.interp(t, np.linspace(0,1,len(pts)), pts[:,1])

def segs(x, y):
    pts = np.column_stack([x, y])
    return np.array([pts[:-1], pts[1:]]).transpose(1,0,2)

# =============================================================================
# VESSEL RENDERING
# =============================================================================
def vessel(ax, pts, wss, w=2.0, alpha=1.0, glow=True, depth=0.0, zo=5, n=250):
    """Draw vessel with multi-layer glow for 3D tube effect."""
    x, y = smooth(pts, n=n)
    sg = segs(x, y)

    wss_v = np.sqrt(wss[0]*wss[1]) if isinstance(wss,(list,tuple)) else wss
    c = np.array(CMAP(NORM(np.clip(wss_v, 0.08, 1500))))
    if depth > 0:
        c[:3] *= (1 - depth * 0.55)

    if glow:
        # Outermost glow — atmosphere (enhanced for dark-bg-only mode)
        gc = c.copy(); gc[3] = 0.05 * alpha
        ax.add_collection(LineCollection(sg, linewidths=w*8, colors=[gc], capstyle='round', zorder=zo-4))
        gc2 = c.copy(); gc2[3] = 0.10 * alpha
        ax.add_collection(LineCollection(sg, linewidths=w*5, colors=[gc2], capstyle='round', zorder=zo-3))
        gc3 = c.copy(); gc3[3] = 0.22 * alpha
        ax.add_collection(LineCollection(sg, linewidths=w*3, colors=[gc3], capstyle='round', zorder=zo-2))
        gc4 = c.copy(); gc4[3] = 0.40 * alpha
        ax.add_collection(LineCollection(sg, linewidths=w*1.6, colors=[gc4], capstyle='round', zorder=zo-1))

    # Main vessel core
    mc = c.copy(); mc[3] = alpha
    ax.add_collection(LineCollection(sg, linewidths=w, colors=[mc], capstyle='round', zorder=zo))

    # Specular highlight (white center line)
    hc = np.minimum(c[:3]*1.3 + 0.4, 1.0)
    hr = np.append(hc, 0.45 * alpha)
    ax.add_collection(LineCollection(sg, linewidths=w*0.25, colors=[hr], capstyle='round', zorder=zo+1))

def vessel_gradient(ax, pts, wss_vals, w=2.0, alpha=1.0, glow=True, zo=5, n=250):
    """Draw vessel with spatially varying WSS color."""
    x, y = smooth(pts, n=n)
    sg = segs(x, y)
    t_w = np.linspace(0, 1, len(wss_vals))
    t_s = np.linspace(0, 1, len(sg))
    wi = np.interp(t_s, t_w, wss_vals)
    cols = CMAP(NORM(np.clip(wi, 0.08, 1500)))
    cols[:, 3] = alpha

    if glow:
        gc = cols.copy(); gc[:, 3] = 0.08 * alpha
        ax.add_collection(LineCollection(sg, linewidths=w*4, colors=gc, capstyle='round', zorder=zo-2))
        gc2 = cols.copy(); gc2[:, 3] = 0.2 * alpha
        ax.add_collection(LineCollection(sg, linewidths=w*2, colors=gc2, capstyle='round', zorder=zo-1))

    ax.add_collection(LineCollection(sg, linewidths=w, colors=cols, capstyle='round', zorder=zo))
    hc = np.minimum(cols[:,:3]*1.3 + 0.3, 1.0)
    hr = np.column_stack([hc, np.full(len(hc), 0.35*alpha)])
    ax.add_collection(LineCollection(sg, linewidths=w*0.2, colors=hr, capstyle='round', zorder=zo+1))

# =============================================================================
# BODY SILHOUETTE (v2 — smoother, gradient-filled)
# =============================================================================
def draw_body(ax):
    # ── RIGHT LEG ──
    r_leg_out = [(57.5, 41), (58, 38), (58.5, 34), (58, 30), (57.5, 26),
                 (57, 22), (56.5, 18), (56, 14), (55.5, 10), (55.5, 7), (56.5, 5)]
    r_leg_in  = [(53, 41), (53.5, 37), (53.5, 33), (53.5, 29), (53.5, 25),
                 (54, 21), (54, 17), (54, 13), (54, 9), (54, 7), (54.5, 5)]
    r_leg = r_leg_out + r_leg_in[::-1]
    ax.fill([p[0] for p in r_leg], [p[1] for p in r_leg],
            color='#141e35', alpha=0.45, zorder=1, edgecolor='#253550', linewidth=0.3)

    # ── LEFT LEG ──
    l_leg = [(100-x, y) for x, y in r_leg]
    ax.fill([p[0] for p in l_leg], [p[1] for p in l_leg],
            color='#141e35', alpha=0.45, zorder=1, edgecolor='#253550', linewidth=0.3)

    # ── TORSO ──
    torso = [(40, 76), (38.5, 73), (38, 68), (38.5, 63), (39, 58),
             (39.5, 53), (40, 49), (41, 45), (42, 42), (43, 41),
             (47, 41), (50, 42), (53, 41), (57, 41), (58, 42),
             (59, 45), (60, 49), (60.5, 53), (61, 58), (61.5, 63),
             (62, 68), (61.5, 73), (60, 76)]
    ax.fill([p[0] for p in torso], [p[1] for p in torso],
            color='#141e35', alpha=0.50, zorder=1, edgecolor='#253550', linewidth=0.3)

    # ── SHOULDERS + NECK ──
    shoulders = [(60, 76), (62, 77), (64, 76.5), (65, 75.5),
                 (64, 74.5), (60.5, 75),   # R shoulder
                 (59, 76.5), (56, 78), (54, 79), (52, 79.5),
                 (50, 80), (48, 79.5), (46, 79), (44, 78),
                 (41, 76.5), (39.5, 75),
                 (36, 74.5), (35, 75.5), (36, 76.5), (38, 77),
                 (40, 76)]
    ax.fill([p[0] for p in shoulders], [p[1] for p in shoulders],
            color='#141e35', alpha=0.45, zorder=1, edgecolor='#253550', linewidth=0.3)

    # ── HEAD ──
    head = Ellipse((50, 88), 12, 14, facecolor='#141e35', edgecolor='#253550',
                    linewidth=0.4, alpha=0.45, zorder=1)
    ax.add_patch(head)

    # ── RIGHT ARM ──
    r_arm_out = [(64.5, 75.5), (65, 73), (65, 70), (64.5, 66), (64, 62),
                 (63.5, 58), (63, 54), (62.5, 50), (62.5, 46), (63, 44)]
    r_arm_in  = [(62, 75), (62.5, 72), (62.5, 68), (62, 64), (61.5, 60),
                 (61.5, 56), (61, 52), (61, 48), (61, 45), (61.5, 43.5)]
    r_arm = r_arm_out + r_arm_in[::-1]
    ax.fill([p[0] for p in r_arm], [p[1] for p in r_arm],
            color='#121c30', alpha=0.38, zorder=1, edgecolor='#253550', linewidth=0.3)

    # ── LEFT ARM ──
    l_arm = [(100-x, y) for x, y in r_arm]
    ax.fill([p[0] for p in l_arm], [p[1] for p in l_arm],
            color='#121c30', alpha=0.38, zorder=1, edgecolor='#253550', linewidth=0.3)

    # ── ORGANS ──
    # Heart (prominent)
    heart = Ellipse((50.5, 67), 5.5, 6.5, angle=-12,
                     facecolor='#3a1225', edgecolor='#882035',
                     linewidth=0.8, alpha=0.5, zorder=2.5)
    ax.add_patch(heart)
    # Heart glow
    heart_g = Ellipse((50.5, 67), 7, 8.5, angle=-12,
                       facecolor='#881530', edgecolor='none',
                       alpha=0.06, zorder=2.3)
    ax.add_patch(heart_g)

    # Lungs
    for lx in [56, 44]:
        lung = Ellipse((lx, 69), 9, 13, facecolor='#111c30',
                         edgecolor='#1e3050', linewidth=0.3, alpha=0.30, zorder=1.5)
        ax.add_patch(lung)

    # Liver
    liver = [(53, 62.5), (56, 63.5), (59.5, 62), (59, 58.5), (56, 57.5), (53, 59)]
    ax.fill([p[0] for p in liver], [p[1] for p in liver],
            color='#261812', edgecolor='#4a3020', linewidth=0.35, alpha=0.4, zorder=1.8)

    # Kidneys
    for kx, ka in [(57.5, 12), (42.5, -12)]:
        k = Ellipse((kx, 55.5), 3, 4.5, angle=ka, facecolor='#18122a',
                      edgecolor='#302548', linewidth=0.3, alpha=0.4, zorder=1.8)
        ax.add_patch(k)

    # Spleen
    sp = Ellipse((40.5, 60), 2.8, 4.2, angle=-18, facecolor='#18122a',
                  edgecolor='#2a2040', linewidth=0.3, alpha=0.35, zorder=1.8)
    ax.add_patch(sp)

    # Brain
    br = Ellipse((50, 89.5), 8, 7, facecolor='#141830',
                  edgecolor='#2a3055', linewidth=0.3, alpha=0.3, zorder=1.5)
    ax.add_patch(br)


# =============================================================================
# CIRCULATORY SYSTEM (v2 — better separation, more detail)
# =============================================================================
def draw_circulation(ax):

    # ===== VEINS FIRST (behind arteries, shifted outward) =====

    # IVC
    vessel(ax, [(52, 66), (52, 62), (52, 58), (52, 54), (52, 50),
                (51.5, 46), (51.5, 42)],
           wss=(1,6), w=3.8, zo=5, depth=0.25)

    # SVC
    vessel(ax, [(52, 66), (53, 69), (54, 72), (54.5, 74.5)],
           wss=(1,6), w=3.2, zo=5, depth=0.2)

    # R Jugular vein
    vessel(ax, [(54.5, 74.5), (54.5, 77), (54, 80), (53.5, 84),
                (53, 87), (53, 90)],
           wss=(1,6), w=1.5, zo=4, depth=0.2)
    # L Jugular
    vessel(ax, [(54.5, 74.5), (52, 76), (49, 78), (47.5, 81),
                (47, 85), (47, 89)],
           wss=(1,6), w=1.5, zo=4, depth=0.2)

    # R arm vein
    vessel(ax, [(54.5, 74.5), (57, 74), (60, 73.5), (63, 72)],
           wss=(1,6), w=1.6, zo=4, depth=0.25)
    vessel(ax, [(63, 72), (63.5, 68), (63, 64), (62.5, 60),
                (62, 56), (62, 52), (62, 48), (62, 45)],
           wss=(1,6), w=1.2, zo=4, depth=0.25)

    # L arm vein
    vessel(ax, [(54.5, 74.5), (51, 75.5), (47, 75), (43, 74), (40, 73.5),
                (37, 72)],
           wss=(1,6), w=1.6, zo=4, depth=0.25)
    vessel(ax, [(37, 72), (36.5, 68), (37, 64), (37.5, 60),
                (38, 56), (38, 52), (38, 48), (38, 45)],
           wss=(1,6), w=1.2, zo=4, depth=0.25)

    # Hepatic vein
    vessel(ax, [(58, 60.5), (56, 62), (54, 63.5), (52, 64.5)],
           wss=(1,6), w=1.1, zo=5, depth=0.15)

    # Portal vein
    vessel(ax, [(51, 49), (52.5, 52), (54, 55), (56, 58), (57, 60)],
           wss=(1,6), w=1.4, zo=4, depth=0.2)

    # Renal veins
    vessel(ax, [(57, 55), (55, 55.5), (53, 55.5), (52, 56)],
           wss=(1,6), w=1.1, zo=4, depth=0.15)
    vessel(ax, [(43, 55.5), (45, 56), (47, 56.5), (48, 56.5)],
           wss=(1,6), w=1.1, zo=4, depth=0.15)

    # R iliac vein → femoral vein
    vessel(ax, [(51.5, 42), (53, 41), (54, 40), (55, 39)],
           wss=(1,6), w=2.2, zo=4, depth=0.2)
    vessel(ax, [(55, 39), (56, 36), (56.5, 32), (57, 28),
                (57, 24), (57, 20), (56.5, 16), (56.5, 12),
                (56.5, 8)],
           wss=(1,6), w=1.4, zo=4, depth=0.2)

    # L iliac vein → femoral vein
    vessel(ax, [(51.5, 42), (50, 41), (49, 40), (48, 39), (47, 39)],
           wss=(1,6), w=2.2, zo=4, depth=0.2)
    vessel(ax, [(47, 39), (46, 36), (45.5, 32), (45, 28),
                (45, 24), (45, 20), (45.5, 16), (45.5, 12),
                (45.5, 8)],
           wss=(1,6), w=1.4, zo=4, depth=0.2)

    # Pulmonary veins
    vessel(ax, [(56.5, 68), (54.5, 67.5), (53, 67), (51.5, 66.5)],
           wss=(1,6), w=1.3, zo=5, depth=0.1)
    vessel(ax, [(43.5, 69), (45.5, 68), (47.5, 67.5), (49, 67)],
           wss=(1,6), w=1.3, zo=5, depth=0.1)

    # ===== ARTERIES (on top, centered) =====

    # Ascending Aorta
    vessel(ax, [(50, 65), (50, 67), (50, 69.5), (50, 72), (50.5, 74)],
           wss=(10,70), w=4.0, zo=10)

    # Aortic Arch
    vessel(ax, [(50.5, 74), (51, 75.5), (50.5, 76.5), (49, 77), (47.5, 76.5)],
           wss=(10,70), w=3.8, zo=10)

    # Descending Aorta
    vessel(ax, [(47.5, 76.5), (48, 74), (48.5, 71), (49, 68),
                (49.5, 64), (49.5, 60), (49.5, 56), (49.5, 52),
                (49.5, 48), (49.5, 44), (50, 42)],
           wss=(10,70), w=3.3, zo=10)

    # R Common Carotid
    vessel(ax, [(50.5, 74.5), (51, 77), (51, 80), (51, 83),
                (51, 86), (51, 89), (51, 92)],
           wss=(10,20), w=1.6, zo=9)

    # L Common Carotid
    vessel(ax, [(49, 77), (48.5, 79), (48.5, 82), (48.5, 85),
                (49, 88), (49, 91)],
           wss=(10,20), w=1.6, zo=9)

    # R Subclavian → Brachial
    vessel(ax, [(50.5, 74.5), (53, 75.5), (56, 76), (59, 75.5),
                (62, 74.5)],
           wss=(10,70), w=2.0, zo=8)
    vessel(ax, [(62, 74.5), (63, 71), (63, 67), (62.5, 63),
                (62, 59), (61.5, 55), (61, 51), (61, 47), (61, 44)],
           wss=(10,70), w=1.4, zo=8)

    # L Subclavian → Brachial
    vessel(ax, [(47.5, 76.5), (45, 76), (42, 75.5), (39, 75),
                (37, 74.5), (35.5, 73.5)],
           wss=(10,70), w=2.0, zo=8)
    vessel(ax, [(35.5, 73.5), (36, 70), (36.5, 66), (37, 62),
                (37.5, 58), (38, 54), (38.5, 50), (39, 46), (39, 44)],
           wss=(10,70), w=1.4, zo=8)

    # Coronary arteries (on heart)
    vessel(ax, [(50, 68), (51.5, 67.5), (52.5, 66.5), (53, 65), (52, 64)],
           wss=(10,70), w=0.8, zo=11)
    vessel(ax, [(50, 68), (48.5, 67), (47.5, 65.5), (48, 64.5)],
           wss=(10,70), w=0.8, zo=11)

    # Pulmonary arteries
    vessel(ax, [(50, 67.5), (52, 68.5), (54, 70), (56, 71)],
           wss=(10,30), w=2.0, zo=7, alpha=0.85)
    vessel(ax, [(50, 67.5), (48, 69), (46, 70.5), (44, 71)],
           wss=(10,30), w=2.0, zo=7, alpha=0.85)

    # Celiac → Hepatic
    vessel(ax, [(49.5, 61), (51, 61.5), (53, 62), (55, 62)],
           wss=(10,70), w=1.3, zo=9)
    vessel(ax, [(55, 62), (57, 61.5), (58.5, 61)],
           wss=(10,70), w=1.0, zo=9)

    # Splenic artery
    vessel(ax, [(49.5, 61), (47.5, 61), (45, 60.5), (42.5, 60), (41, 59.5)],
           wss=(10,70), w=0.9, zo=8)

    # Renal arteries
    vessel(ax, [(49.5, 56), (51, 56.5), (53, 56.5), (55, 56.5),
                (57, 56)],
           wss=(10,70), w=1.3, zo=9)
    vessel(ax, [(49.5, 57), (47.5, 57), (45.5, 57), (43.5, 56.5)],
           wss=(10,70), w=1.3, zo=9)

    # Mesenteric
    vessel(ax, [(49.5, 54), (51, 53), (53, 52), (54.5, 50.5)],
           wss=(10,70), w=0.8, zo=8)
    vessel(ax, [(49.5, 51), (48, 50), (46.5, 49)],
           wss=(10,70), w=0.8, zo=8)

    # Iliac → Femoral (right)
    vessel(ax, [(50, 42), (51, 41), (52, 40), (53, 39), (54, 38)],
           wss=(10,70), w=2.4, zo=10)
    vessel(ax, [(54, 38), (54.5, 35), (55, 31), (55, 27),
                (55, 23), (55, 19), (55, 15), (55, 11),
                (55, 7)],
           wss=(10,70), w=1.8, zo=9)

    # Iliac → Femoral (left)
    vessel(ax, [(50, 42), (49, 41), (48, 40), (47, 39), (46, 38)],
           wss=(10,70), w=2.4, zo=10)
    vessel(ax, [(46, 38), (45.5, 35), (45, 31), (45, 27),
                (45, 23), (45, 19), (45, 15), (45, 11),
                (45, 7)],
           wss=(10,70), w=1.8, zo=9)

    # ===== ARTERIOLES (thin, high WSS ~55) =====
    vessel(ax, [(57, 56), (58.5, 55.5), (59.5, 55)],
           wss=(40,60), w=0.5, zo=8)
    vessel(ax, [(43.5, 56.5), (42, 56), (41, 55.5)],
           wss=(40,60), w=0.5, zo=8)

    # Hepatic arteriole → sinusoidal transition (gradient)
    vessel_gradient(ax, [(58.5, 61), (59, 60), (59.5, 59), (59, 58)],
                    wss_vals=[50, 15, 3, 0.3], w=0.5, zo=9)

    # ===== LYMPHATIC (deep blue, behind everything) =====
    vessel(ax, [(48, 42), (47.5, 48), (47, 54), (46.5, 60),
                (46.5, 66), (46.5, 72), (47, 76)],
           wss=(0.1,0.6), w=0.7, zo=3, alpha=0.65)
    vessel(ax, [(54, 74), (55, 75.5)],
           wss=(0.1,0.6), w=0.4, zo=3, alpha=0.55)

    # ===== MICROVASCULAR BEDS =====
    np.random.seed(42)

    # Hepatic sinusoids
    n = 400
    sx = 56 + np.random.normal(0, 1.8, n)
    sy = 60 + np.random.normal(0, 1.5, n)
    sw = np.random.uniform(0.1, 0.6, n)
    sc = CMAP(NORM(sw))
    sc[:, 3] = np.random.uniform(0.12, 0.55, n)
    ax.scatter(sx, sy, s=np.random.uniform(0.5, 8, n), c=sc, zorder=3, edgecolors='none')

    # Kidney beds
    for kx, ky in [(57.5, 55.5), (42.5, 55.5)]:
        n_k = 100
        kxp = kx + np.random.normal(0, 1.0, n_k)
        kyp = ky + np.random.normal(0, 1.5, n_k)
        kw = np.random.uniform(0.5, 8, n_k)
        kc = CMAP(NORM(kw)); kc[:, 3] = 0.25
        ax.scatter(kxp, kyp, s=np.random.uniform(0.5, 4, n_k), c=kc, zorder=2, edgecolors='none')

    # Pulmonary capillary beds
    for lx, ly in [(56, 69.5), (44, 69.5)]:
        n_l = 150
        lxp = lx + np.random.normal(0, 2.8, n_l)
        lyp = ly + np.random.normal(0, 4, n_l)
        lw = np.random.uniform(1, 12, n_l)
        lc = CMAP(NORM(lw)); lc[:, 3] = 0.12
        ax.scatter(lxp, lyp, s=np.random.uniform(0.5, 3, n_l), c=lc, zorder=1.5, edgecolors='none')

    # Intestinal capillary bed
    n_i = 120
    ix = 51 + np.random.normal(0, 2.5, n_i)
    iy = 50 + np.random.normal(0, 2.5, n_i)
    iw = np.random.uniform(2, 20, n_i)
    ic = CMAP(NORM(iw)); ic[:, 3] = 0.12
    ax.scatter(ix, iy, s=np.random.uniform(0.5, 4, n_i), c=ic, zorder=1.5, edgecolors='none')


# =============================================================================
# PATHOLOGICAL MARKERS
# =============================================================================
def draw_pathology(ax):
    # Atherosclerotic site (carotid bifurcation)
    ax.plot(51, 83, 'D', color='#ffdd33', markersize=7, zorder=20,
            markeredgecolor='white', markeredgewidth=0.5)
    circ = Circle((51, 83), 2, facecolor='none', edgecolor='#ffdd33',
                   linewidth=0.7, alpha=0.35, linestyle='--', zorder=19)
    ax.add_patch(circ)
    ax.annotate('Atherosclerotic Plaque\nWSS < 4 dyne/cm\u00b2\nLow/oscillatory flow promotes\nendothelial dysfunction',
                xy=(51, 83), xytext=(65, 86),
                fontsize=6, color='#ffdd88', fontweight='bold', ha='left', va='center',
                arrowprops=dict(arrowstyle='->', color='#ffdd88', lw=0.7,
                                connectionstyle='arc3,rad=0.12'),
                bbox=dict(boxstyle='round,pad=0.35', facecolor='#111828',
                          edgecolor='#ffdd44', alpha=0.9, linewidth=0.5),
                zorder=25)

    # Stenotic hotspot
    ax.plot(51.5, 79.5, '*', color='#ff2233', markersize=10, zorder=20,
            markeredgecolor='white', markeredgewidth=0.3)
    Circle((51.5, 79.5), 1.5, facecolor='#ff0000', edgecolor='none',
           alpha=0.08, zorder=18)
    ax.annotate('Stenotic Hotspot\nWSS > 1000 dyne/cm\u00b2\nRuptures lipid bilayers\n& strips hydration shells',
                xy=(51.5, 79.5), xytext=(65, 78),
                fontsize=6, color='#ff8888', fontweight='bold', ha='left', va='center',
                arrowprops=dict(arrowstyle='->', color='#ff8888', lw=0.7,
                                connectionstyle='arc3,rad=-0.08'),
                bbox=dict(boxstyle='round,pad=0.35', facecolor='#111020',
                          edgecolor='#ff4444', alpha=0.9, linewidth=0.5),
                zorder=25)

    # Tumor vasculature
    np.random.seed(77)
    nt = 70
    tx = 44 + np.random.normal(0, 1.0, nt)
    ty = 71 + np.random.normal(0, 1.2, nt)
    tw = np.random.uniform(0.3, 4, nt)
    tc = CMAP(NORM(tw)); tc[:, 3] = 0.5
    ax.scatter(tx, ty, s=np.random.uniform(2, 12, nt), c=tc, zorder=15,
               edgecolors='none', marker='s')
    tc2 = Circle((44, 71), 2.2, facecolor='none', edgecolor='#ff4466',
                  linewidth=0.5, linestyle=':', alpha=0.45, zorder=14)
    ax.add_patch(tc2)
    ax.annotate('Tumor Vasculature\nLow & oscillatory WSS\nChaotic architecture impairs\nnanoparticle penetration',
                xy=(44, 71), xytext=(28, 74),
                fontsize=6, color='#ff8899', fontweight='bold', ha='right', va='center',
                arrowprops=dict(arrowstyle='->', color='#ff8899', lw=0.7,
                                connectionstyle='arc3,rad=0.12'),
                bbox=dict(boxstyle='round,pad=0.35', facecolor='#111020',
                          edgecolor='#ff4466', alpha=0.9, linewidth=0.5),
                zorder=25)

    # Hepatic sinusoidal annotation
    ax.annotate('Hepatic Sinusoidal Bed\nWSS 0.1\u20130.6 dyne/cm\u00b2\nFenestrated endothelium;\nNP margination zone',
                xy=(57, 60), xytext=(65, 60),
                fontsize=6, color='#6688cc', fontweight='bold', ha='left', va='center',
                arrowprops=dict(arrowstyle='->', color='#6688cc', lw=0.7,
                                connectionstyle='arc3,rad=-0.08'),
                bbox=dict(boxstyle='round,pad=0.35', facecolor='#0a1028',
                          edgecolor='#4466aa', alpha=0.9, linewidth=0.5),
                zorder=25)

    # Arteriole annotation
    ax.annotate('Arterioles\nWSS ~55 dyne/cm\u00b2\nHigh shear drives\nnanoparticle margination',
                xy=(59, 55), xytext=(65, 52),
                fontsize=6, color='#ffaa44', fontweight='bold', ha='left', va='center',
                arrowprops=dict(arrowstyle='->', color='#ffaa44', lw=0.7,
                                connectionstyle='arc3,rad=0.1'),
                bbox=dict(boxstyle='round,pad=0.35', facecolor='#181510',
                          edgecolor='#cc8822', alpha=0.9, linewidth=0.5),
                zorder=25)


# =============================================================================
# ORGAN LABELS
# =============================================================================
def draw_labels(ax):
    labels = [
        (50, 89.5, 'Brain', '#445575', 6),
        (50.5, 67, '\u2764', '#bb2535', 10),
        (56, 70, 'R. Lung', '#1e3550', 5.5),
        (44, 70, 'L. Lung', '#1e3550', 5.5),
        (56, 62.5, 'Liver', '#4a3525', 5.5),
        (57.5, 55.5, 'Kidney', '#302245', 5),
        (42.5, 55.5, 'Kidney', '#302245', 5),
        (40.5, 60.5, 'Spleen', '#2a2040', 5),
    ]
    for x, y, t, c, fs in labels:
        ax.text(x, y, t, fontsize=fs, color=c, ha='center', va='center',
                fontstyle='italic', alpha=0.6, zorder=3)


# =============================================================================
# WSS TABLE
# =============================================================================
def draw_table(ax_t):
    ax_t.set_facecolor('#0a0f1c')
    ax_t.set_xlim(0, 10); ax_t.set_ylim(0, 10); ax_t.axis('off')

    ax_t.text(5, 9.6, 'Wall Shear Stress Reference Data', fontsize=9,
              color='white', ha='center', va='top', fontweight='bold')

    data = [
        ('Hepatic Sinusoids', 0.1, 0.6, 'Ultra-low; fenestrated endothelium; NP access'),
        ('Lymphatic Vessels', 0.1, 0.6, 'Near-stagnant drainage flow'),
        ('Venous Circulation', 1, 6, 'Low-pressure, high-capacitance return'),
        ('Atherosclerotic Sites', 0.5, 4, 'Pathological; promotes plaque formation'),
        ('Carotid Arteries', 10, 20, 'Maintains endothelial homeostasis'),
        ('Arterioles', 40, 60, 'High shear drives NP margination'),
        ('General Arterial', 10, 70, 'Pulsatile systemic circulation'),
        ('Stenotic Regions', 100, 1200, 'Extreme shear; bilayer rupture risk'),
    ]

    y = 9.0
    for region, lo, hi, note in data:
        y -= 1.0
        wm = np.sqrt(lo * hi)
        c = CMAP(NORM(wm))
        r = FancyBboxPatch((0.3, y-0.3), 0.6, 0.6,
                            boxstyle='round,pad=0.05', facecolor=c,
                            edgecolor='none', alpha=0.9)
        ax_t.add_patch(r)
        ax_t.text(1.2, y, region, fontsize=6.5, color='#ccddee', ha='left',
                  va='center', fontweight='bold')
        wt = f'{lo}\u2013{hi}' if hi < 1000 else f'{lo}\u2013{hi}+'
        ax_t.text(5.8, y, wt, fontsize=6, color='#aabbcc', ha='center',
                  va='center', family='monospace')
        ax_t.text(7.0, y, note, fontsize=4.8, color='#778899', ha='left',
                  va='center', fontstyle='italic')

    ax_t.text(5.8, y - 1.0, 'dyne/cm\u00b2', fontsize=5, color='#556677',
              ha='center', fontstyle='italic')


# =============================================================================
# ASSEMBLY
# =============================================================================
def build():
    fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=BG)

    gs = gridspec.GridSpec(2, 2, width_ratios=[3.5, 1], height_ratios=[5.5, 1],
                           hspace=0.02, wspace=0.02,
                           left=0.02, right=0.98, top=0.96, bottom=0.02)

    ax = fig.add_subplot(gs[0, 0])
    ax.set_facecolor(BG)
    ax.set_xlim(30, 72)
    ax.set_ylim(0, 100)
    ax.set_aspect('equal')
    ax.axis('off')

    ax_cb_area = fig.add_subplot(gs[0, 1])
    ax_cb_area.set_facecolor(BG)
    ax_cb_area.axis('off')

    ax_t = fig.add_subplot(gs[1, :])

    # Background vignette
    grad = np.linspace(0, 1, 256).reshape(1, -1).T
    bcm = LinearSegmentedColormap.from_list('b', ['#040810', '#0c1425', '#040810'])
    ax.imshow(grad, aspect='auto', cmap=bcm, alpha=0.25, extent=[30,72,0,100], zorder=0)

    print('  Vessels...'); draw_circulation(ax)
    print('  Pathology...'); draw_pathology(ax)

    # Title
    fig.text(0.38, 0.975,
             'Wall Shear Stress Distribution\nin the Human Circulatory System',
             fontsize=17, color='white', ha='center', va='top',
             fontweight='bold', linespacing=1.3)
    fig.text(0.38, 0.94,
             'Color intensity represents WSS magnitude (logarithmic scale, 0.1\u20131000+ dyne/cm\u00b2)',
             fontsize=8, color='#7888a0', ha='center', va='top', fontstyle='italic')

    # Colorbar
    print('  Colorbar...')
    cb_l, cb_b, cb_w, cb_h = 0.82, 0.22, 0.025, 0.55
    ax_cb = fig.add_axes([cb_l, cb_b, cb_w, cb_h])
    ax_cb.set_facecolor('none')
    cb = ColorbarBase(ax_cb, cmap=CMAP, norm=NORM, orientation='vertical')
    cb.set_label('Wall Shear Stress (dyne/cm\u00b2)', fontsize=9, color='white', labelpad=10)
    cb.set_ticks([0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000])
    cb.set_ticklabels(['0.1', '0.5', '1', '5', '10', '50', '100', '500', '1000'])
    cb.ax.tick_params(colors='white', labelsize=7)
    cb.outline.set_edgecolor('#2a3548')
    cb.outline.set_linewidth(0.5)

    # Colorbar region annotations
    cba = [
        (0.3, 'Sinusoids &\nLymphatics', '#3355aa'),
        (3,   'Veins', '#00aacc'),
        (15,  'Carotid\nArteries', '#66bb00'),
        (55,  'Arterioles', '#ffaa00'),
        (400, 'Stenosis', '#cc0044'),
    ]
    for wv, lb, cl in cba:
        yn = NORM(wv)
        fig.text(cb_l + cb_w + 0.035, cb_b + yn * cb_h,
                 lb, fontsize=5.5, color=cl, ha='left', va='center',
                 fontweight='bold', fontstyle='italic')
        tl = Line2D([cb_l+cb_w+0.005, cb_l+cb_w+0.025],
                    [cb_b+yn*cb_h]*2, color=cl, lw=0.5, alpha=0.5,
                    transform=fig.transFigure, clip_on=False)
        fig.add_artist(tl)

    # Legend
    legs = [
        Line2D([0],[0], color=CMAP(NORM(30)), lw=3.5, label='Arterial (10\u201370 dyne/cm\u00b2)'),
        Line2D([0],[0], color=CMAP(NORM(3)), lw=3.5, label='Venous (1\u20136 dyne/cm\u00b2)'),
        Line2D([0],[0], color=CMAP(NORM(0.3)), lw=1.5, label='Lymphatic (0.1\u20130.6 dyne/cm\u00b2)'),
        Line2D([0],[0], color=CMAP(NORM(55)), lw=1, label='Arterioles (~55 dyne/cm\u00b2)'),
        Line2D([0],[0], marker='D', color='w', markerfacecolor='#ffdd33', markersize=6,
               lw=0, label='Atherosclerotic site (<4)'),
        Line2D([0],[0], marker='*', color='w', markerfacecolor='#ff2233', markersize=8,
               lw=0, label='Stenotic hotspot (>1000)'),
    ]
    lg = ax.legend(handles=legs, loc='lower left', fontsize=6.5,
                    facecolor='#0c1220', edgecolor='#2a3548',
                    labelcolor='#bbccdd', framealpha=0.92,
                    borderpad=0.8, handlelength=2.5, handletextpad=0.6,
                    title='Vessel Type', title_fontsize=7)
    lg.get_title().set_color('#8899aa')
    lg.get_title().set_fontweight('bold')

    # Table
    print('  Table...'); draw_table(ax_t)

    # Citation
    fig.text(0.5, 0.005,
             'Data: Modh et al., \u201cResolving the Biomechanical Blind Spot '
             'in Nanomedicine Translation\u201d \u2014 ACS Nano (2025)',
             fontsize=6, color='#445566', ha='center', va='bottom', fontstyle='italic')

    return fig


def main():
    print('Generating v2 WSS figure...')
    fig = build()

    import os
    out = '/Users/harsh/Desktop/work/1_Review Article/shear-stress-3d-viz/wss_circulatory_v3.png'
    out_pdf = out.replace('.png', '.pdf')

    print(f'  Saving PNG ({DPI} DPI)...')
    fig.savefig(out, dpi=DPI, facecolor=BG, bbox_inches='tight', pad_inches=0.1)
    print(f'  Saving PDF (vector)...')
    fig.savefig(out_pdf, facecolor=BG, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)

    sz = os.path.getsize(out) / (1024*1024)
    print(f'\nDone!\n  PNG: {out} ({sz:.1f} MB)\n  PDF: {out_pdf}')


if __name__ == '__main__':
    main()
