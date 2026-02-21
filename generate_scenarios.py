#!/usr/bin/env python3
"""
Scenario-Based WSS Visualizations of the Human Circulatory System
=================================================================

Generates multiple figures showing how different pathologies alter
the hemodynamic landscape:

  1. Healthy Baseline — Normal circulatory WSS distribution
  2. Lung Cancer — Tumor vasculature in pulmonary region
  3. Liver Cancer (HCC) — Disrupted hepatic sinusoidal flow
  4. Brain Tumor (Glioblastoma) — Altered cerebral hemodynamics
  5. Multi-Site Atherosclerosis — Plaque at multiple arterial locations
  6. Multi-Site Stenosis — Severe narrowing at multiple sites
  7. Combined Severe Pathology — All pathologies co-existing

All figures share the same circulatory base, colormap, and style.

Usage:
    python generate_scenarios.py          # all scenarios
    python generate_scenarios.py healthy  # specific scenario
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.patches import FancyBboxPatch, Circle, Ellipse
from matplotlib.lines import Line2D
from matplotlib.colorbar import ColorbarBase
from scipy.interpolate import splprep, splev
import matplotlib.gridspec as gridspec
import os, sys
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIG
# =============================================================================
DPI = 300
FIG_W, FIG_H = 14, 18
BG = '#080c18'
OUT_DIR = '/Users/harsh/Desktop/work/1_Review Article/shear-stress-3d-viz/scenarios'

# WSS colormap
_wss_pts = [
    (0.00, '#060840'), (0.10, '#0030aa'), (0.20, '#0088dd'),
    (0.30, '#00bbaa'), (0.42, '#22cc44'), (0.52, '#99dd00'),
    (0.62, '#eedd00'), (0.72, '#ff9900'), (0.82, '#ff3300'),
    (0.92, '#cc0055'), (1.00, '#9900cc'),
]

def _h2r(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16)/255 for i in (0,2,4))

def _make_cmap():
    cd = {'red':[], 'green':[], 'blue':[]}
    for p, h in _wss_pts:
        r, g, b = _h2r(h)
        cd['red'].append((p,r,r)); cd['green'].append((p,g,g)); cd['blue'].append((p,b,b))
    return LinearSegmentedColormap('wss', cd, N=512)

CMAP = _make_cmap()
NORM = LogNorm(vmin=0.08, vmax=1500)


# =============================================================================
# CURVE + VESSEL UTILITIES
# =============================================================================
def smooth(pts, n=250):
    pts = np.array(pts, dtype=float)
    if len(pts) < 3:
        t = np.linspace(0, 1, n)
        return pts[0,0]+(pts[-1,0]-pts[0,0])*t, pts[0,1]+(pts[-1,1]-pts[0,1])*t
    try:
        tck, _ = splprep([pts[:,0], pts[:,1]], s=0, k=min(3, len(pts)-1))
        return splev(np.linspace(0,1,n), tck)
    except:
        t = np.linspace(0,1,n)
        return np.interp(t, np.linspace(0,1,len(pts)), pts[:,0]), \
               np.interp(t, np.linspace(0,1,len(pts)), pts[:,1])

def _segs(x, y):
    pts = np.column_stack([x, y])
    return np.array([pts[:-1], pts[1:]]).transpose(1,0,2)

def vessel(ax, pts, wss, w=2.0, alpha=1.0, glow=True, depth=0.0, zo=5, n=250):
    x, y = smooth(pts, n=n)
    sg = _segs(x, y)
    wss_v = np.sqrt(wss[0]*wss[1]) if isinstance(wss,(list,tuple)) else wss
    c = np.array(CMAP(NORM(np.clip(wss_v, 0.08, 1500))))
    if depth > 0: c[:3] *= (1 - depth*0.55)
    if glow:
        for mult, a in [(8, 0.05), (5, 0.10), (3, 0.22), (1.6, 0.40)]:
            gc = c.copy(); gc[3] = a*alpha
            ax.add_collection(LineCollection(sg, linewidths=w*mult, colors=[gc],
                              capstyle='round', zorder=zo-4))
    mc = c.copy(); mc[3] = alpha
    ax.add_collection(LineCollection(sg, linewidths=w, colors=[mc], capstyle='round', zorder=zo))
    hc = np.minimum(c[:3]*1.3+0.4, 1.0)
    hr = np.append(hc, 0.45*alpha)
    ax.add_collection(LineCollection(sg, linewidths=w*0.25, colors=[hr], capstyle='round', zorder=zo+1))

def vessel_gradient(ax, pts, wss_vals, w=2.0, alpha=1.0, glow=True, zo=5, n=250):
    x, y = smooth(pts, n=n)
    sg = _segs(x, y)
    t_w = np.linspace(0,1,len(wss_vals)); t_s = np.linspace(0,1,len(sg))
    wi = np.interp(t_s, t_w, wss_vals)
    cols = CMAP(NORM(np.clip(wi, 0.08, 1500))); cols[:,3] = alpha
    if glow:
        gc = cols.copy(); gc[:,3] = 0.1*alpha
        ax.add_collection(LineCollection(sg, linewidths=w*4, colors=gc, capstyle='round', zorder=zo-2))
        gc2 = cols.copy(); gc2[:,3] = 0.25*alpha
        ax.add_collection(LineCollection(sg, linewidths=w*2, colors=gc2, capstyle='round', zorder=zo-1))
    ax.add_collection(LineCollection(sg, linewidths=w, colors=cols, capstyle='round', zorder=zo))
    hc = np.minimum(cols[:,:3]*1.3+0.3, 1.0)
    hr = np.column_stack([hc, np.full(len(hc), 0.35*alpha)])
    ax.add_collection(LineCollection(sg, linewidths=w*0.2, colors=hr, capstyle='round', zorder=zo+1))

def scatter_bed(ax, cx, cy, sx, sy, n, wss_lo, wss_hi, alpha_range=(0.12, 0.55),
                size_range=(0.5, 8), zo=3, marker='o', seed=42):
    np.random.seed(seed)
    phi = np.random.uniform(0, 2*np.pi, n)
    r = np.random.uniform(0.2, 1.0, n)**(0.5)
    x = cx + r*sx*np.cos(phi); y = cy + r*sy*np.sin(phi)
    w = np.random.uniform(wss_lo, wss_hi, n)
    c = CMAP(NORM(w)); c[:,3] = np.random.uniform(*alpha_range, n)
    ax.scatter(x, y, s=np.random.uniform(*size_range, n), c=c, zorder=zo,
              edgecolors='none', marker=marker)

def annotation(ax, text, xy, xytext, color, edge_color=None, fontsize=6.5,
               rad=0.12, zo=25):
    if edge_color is None: edge_color = color
    ax.annotate(text, xy=xy, xytext=xytext,
                fontsize=fontsize, color=color, fontweight='bold',
                ha='left' if xytext[0]>xy[0] else 'right', va='center',
                arrowprops=dict(arrowstyle='->', color=color, lw=0.7,
                                connectionstyle=f'arc3,rad={rad}'),
                bbox=dict(boxstyle='round,pad=0.35', facecolor='#0c1020',
                          edgecolor=edge_color, alpha=0.92, linewidth=0.5),
                zorder=zo)


# =============================================================================
# SHARED CIRCULATORY BASE
# =============================================================================
def draw_base_circulation(ax):
    """Draw the complete healthy circulatory system (arteries + veins + lymph)."""

    # ── VEINS (behind, depth-faded) ──
    vessel(ax, [(52,66),(52,62),(52,58),(52,54),(52,50),(51.5,46),(51.5,42)],
           wss=(1,6), w=3.8, zo=5, depth=0.25)
    vessel(ax, [(52,66),(53,69),(54,72),(54.5,74.5)],
           wss=(1,6), w=3.2, zo=5, depth=0.2)
    vessel(ax, [(54.5,74.5),(54.5,77),(54,80),(53.5,84),(53,87),(53,90)],
           wss=(1,6), w=1.5, zo=4, depth=0.2)
    vessel(ax, [(54.5,74.5),(52,76),(49,78),(47.5,81),(47,85),(47,89)],
           wss=(1,6), w=1.5, zo=4, depth=0.2)
    vessel(ax, [(54.5,74.5),(57,74),(60,73.5),(63,72)],
           wss=(1,6), w=1.6, zo=4, depth=0.25)
    vessel(ax, [(63,72),(63.5,68),(63,64),(62.5,60),(62,56),(62,52),(62,48),(62,45)],
           wss=(1,6), w=1.2, zo=4, depth=0.25)
    vessel(ax, [(54.5,74.5),(51,75.5),(47,75),(43,74),(40,73.5),(37,72)],
           wss=(1,6), w=1.6, zo=4, depth=0.25)
    vessel(ax, [(37,72),(36.5,68),(37,64),(37.5,60),(38,56),(38,52),(38,48),(38,45)],
           wss=(1,6), w=1.2, zo=4, depth=0.25)
    vessel(ax, [(58,60.5),(56,62),(54,63.5),(52,64.5)],
           wss=(1,6), w=1.1, zo=5, depth=0.15)
    vessel(ax, [(51,49),(52.5,52),(54,55),(56,58),(57,60)],
           wss=(1,6), w=1.4, zo=4, depth=0.2)
    vessel(ax, [(57,55),(55,55.5),(53,55.5),(52,56)],
           wss=(1,6), w=1.1, zo=4, depth=0.15)
    vessel(ax, [(43,55.5),(45,56),(47,56.5),(48,56.5)],
           wss=(1,6), w=1.1, zo=4, depth=0.15)
    vessel(ax, [(51.5,42),(53,41),(54,40),(55,39)],
           wss=(1,6), w=2.2, zo=4, depth=0.2)
    vessel(ax, [(55,39),(56,36),(56.5,32),(57,28),(57,24),(57,20),(56.5,16),(56.5,12),(56.5,8)],
           wss=(1,6), w=1.4, zo=4, depth=0.2)
    vessel(ax, [(51.5,42),(50,41),(49,40),(48,39),(47,39)],
           wss=(1,6), w=2.2, zo=4, depth=0.2)
    vessel(ax, [(47,39),(46,36),(45.5,32),(45,28),(45,24),(45,20),(45.5,16),(45.5,12),(45.5,8)],
           wss=(1,6), w=1.4, zo=4, depth=0.2)
    vessel(ax, [(56.5,68),(54.5,67.5),(53,67),(51.5,66.5)],
           wss=(1,6), w=1.3, zo=5, depth=0.1)
    vessel(ax, [(43.5,69),(45.5,68),(47.5,67.5),(49,67)],
           wss=(1,6), w=1.3, zo=5, depth=0.1)

    # ── ARTERIES ──
    vessel(ax, [(50,65),(50,67),(50,69.5),(50,72),(50.5,74)],
           wss=(10,70), w=4.0, zo=10)
    vessel(ax, [(50.5,74),(51,75.5),(50.5,76.5),(49,77),(47.5,76.5)],
           wss=(10,70), w=3.8, zo=10)
    vessel(ax, [(47.5,76.5),(48,74),(48.5,71),(49,68),(49.5,64),(49.5,60),
                (49.5,56),(49.5,52),(49.5,48),(49.5,44),(50,42)],
           wss=(10,70), w=3.3, zo=10)
    vessel(ax, [(50.5,74.5),(51,77),(51,80),(51,83),(51,86),(51,89),(51,92)],
           wss=(10,20), w=1.6, zo=9)
    vessel(ax, [(49,77),(48.5,79),(48.5,82),(48.5,85),(49,88),(49,91)],
           wss=(10,20), w=1.6, zo=9)
    vessel(ax, [(50.5,74.5),(53,75.5),(56,76),(59,75.5),(62,74.5)],
           wss=(10,70), w=2.0, zo=8)
    vessel(ax, [(62,74.5),(63,71),(63,67),(62.5,63),(62,59),(61.5,55),(61,51),(61,47),(61,44)],
           wss=(10,70), w=1.4, zo=8)
    vessel(ax, [(47.5,76.5),(45,76),(42,75.5),(39,75),(37,74.5),(35.5,73.5)],
           wss=(10,70), w=2.0, zo=8)
    vessel(ax, [(35.5,73.5),(36,70),(36.5,66),(37,62),(37.5,58),(38,54),(38.5,50),(39,46),(39,44)],
           wss=(10,70), w=1.4, zo=8)
    vessel(ax, [(50,68),(51.5,67.5),(52.5,66.5),(53,65),(52,64)],
           wss=(10,70), w=0.8, zo=11)
    vessel(ax, [(50,68),(48.5,67),(47.5,65.5),(48,64.5)],
           wss=(10,70), w=0.8, zo=11)
    vessel(ax, [(50,67.5),(52,68.5),(54,70),(56,71)],
           wss=(10,30), w=2.0, zo=7, alpha=0.85)
    vessel(ax, [(50,67.5),(48,69),(46,70.5),(44,71)],
           wss=(10,30), w=2.0, zo=7, alpha=0.85)
    vessel(ax, [(49.5,61),(51,61.5),(53,62),(55,62)],
           wss=(10,70), w=1.3, zo=9)
    vessel(ax, [(55,62),(57,61.5),(58.5,61)],
           wss=(10,70), w=1.0, zo=9)
    vessel(ax, [(49.5,61),(47.5,61),(45,60.5),(42.5,60),(41,59.5)],
           wss=(10,70), w=0.9, zo=8)
    vessel(ax, [(49.5,56),(51,56.5),(53,56.5),(55,56.5),(57,56)],
           wss=(10,70), w=1.3, zo=9)
    vessel(ax, [(49.5,57),(47.5,57),(45.5,57),(43.5,56.5)],
           wss=(10,70), w=1.3, zo=9)
    vessel(ax, [(49.5,54),(51,53),(53,52),(54.5,50.5)],
           wss=(10,70), w=0.8, zo=8)
    vessel(ax, [(49.5,51),(48,50),(46.5,49)],
           wss=(10,70), w=0.8, zo=8)
    vessel(ax, [(50,42),(51,41),(52,40),(53,39),(54,38)],
           wss=(10,70), w=2.4, zo=10)
    vessel(ax, [(54,38),(54.5,35),(55,31),(55,27),(55,23),(55,19),(55,15),(55,11),(55,7)],
           wss=(10,70), w=1.8, zo=9)
    vessel(ax, [(50,42),(49,41),(48,40),(47,39),(46,38)],
           wss=(10,70), w=2.4, zo=10)
    vessel(ax, [(46,38),(45.5,35),(45,31),(45,27),(45,23),(45,19),(45,15),(45,11),(45,7)],
           wss=(10,70), w=1.8, zo=9)

    # Arterioles
    vessel(ax, [(57,56),(58.5,55.5),(59.5,55)], wss=(40,60), w=0.5, zo=8)
    vessel(ax, [(43.5,56.5),(42,56),(41,55.5)], wss=(40,60), w=0.5, zo=8)
    vessel_gradient(ax, [(58.5,61),(59,60),(59.5,59),(59,58)],
                    wss_vals=[50,15,3,0.3], w=0.5, zo=9)

    # Lymphatic
    vessel(ax, [(48,42),(47.5,48),(47,54),(46.5,60),(46.5,66),(46.5,72),(47,76)],
           wss=(0.1,0.6), w=0.7, zo=3, alpha=0.65)
    vessel(ax, [(54,74),(55,75.5)], wss=(0.1,0.6), w=0.4, zo=3, alpha=0.55)

    # Healthy microvascular beds
    scatter_bed(ax, 56, 60, 1.8, 1.5, 400, 0.1, 0.6, seed=42)       # hepatic sinusoids
    for kx in [57.5, 42.5]:
        scatter_bed(ax, kx, 55.5, 1.0, 1.5, 100, 0.5, 8, alpha_range=(0.15,0.3),
                    size_range=(0.5,4), seed=int(kx*10), zo=2)
    for lx in [56, 44]:
        scatter_bed(ax, lx, 69.5, 2.8, 4, 150, 1, 12, alpha_range=(0.08,0.18),
                    size_range=(0.5,3), seed=int(lx*10), zo=1.5)
    scatter_bed(ax, 51, 50, 2.5, 2.5, 120, 2, 20, alpha_range=(0.08,0.15),
                size_range=(0.5,4), seed=99, zo=1.5)


# =============================================================================
# SCENARIO-SPECIFIC OVERLAYS
# =============================================================================

def overlay_healthy(ax):
    """Healthy baseline — annotations for normal physiology."""
    annotation(ax, 'Carotid Arteries\nWSS 10\u201320 dyne/cm\u00b2\nAnti-inflammatory\nendothelial phenotype',
               (51, 86), (64, 88), '#88cc44')
    annotation(ax, 'Aorta\nWSS 10\u201370 dyne/cm\u00b2\nPulsatile systemic conduit',
               (49.5, 64), (35, 64), '#ccdd00', rad=-0.1)
    annotation(ax, 'Hepatic Sinusoids\nWSS 0.1\u20130.6 dyne/cm\u00b2\nUltra-low shear;\nfenestrated endothelium',
               (57, 60), (65, 60), '#4466bb')
    annotation(ax, 'Venous Return\nWSS 1\u20136 dyne/cm\u00b2\nLow-pressure, high-capacitance',
               (52, 54), (35, 53), '#00aacc', rad=0.1)
    annotation(ax, 'Arterioles\nWSS ~55 dyne/cm\u00b2\nDrives NP margination',
               (59, 55), (65, 52), '#ffaa44')


def overlay_lung_cancer(ax):
    """Lung cancer — tumor vasculature in both lungs."""
    # Right lung tumor
    scatter_bed(ax, 57, 71, 2.5, 2.5, 150, 0.2, 3, alpha_range=(0.25,0.6),
                size_range=(2,12), seed=111, marker='s', zo=15)
    circ = Circle((57, 71), 3.5, facecolor='none', edgecolor='#ff4466',
                   lw=0.8, ls=':', alpha=0.6, zorder=14)
    ax.add_patch(circ)
    annotation(ax, 'R. Lung Tumor\nWSS 0.2\u20133 dyne/cm\u00b2\nChaotic vasculature;\nelevated interstitial pressure;\nimpaired NP penetration',
               (57, 71), (65, 74), '#ff6688', edge_color='#ff4466')

    # Left lung tumor (smaller, metastatic)
    scatter_bed(ax, 43, 68, 1.8, 2, 80, 0.3, 4, alpha_range=(0.25,0.55),
                size_range=(2,10), seed=222, marker='s', zo=15)
    circ2 = Circle((43, 68), 2.5, facecolor='none', edgecolor='#ff4466',
                    lw=0.6, ls=':', alpha=0.5, zorder=14)
    ax.add_patch(circ2)
    annotation(ax, 'L. Lung Metastasis\nWSS 0.3\u20134 dyne/cm\u00b2\nDisorganized angiogenesis',
               (43, 68), (28, 67), '#ff6688', edge_color='#ff4466', rad=-0.1)

    # Tumor-feeding artery (altered WSS gradient)
    vessel_gradient(ax, [(54, 70), (55.5, 70.5), (56.5, 71)],
                    wss_vals=[15, 5, 1], w=0.8, zo=16)

    # General note
    annotation(ax, 'Pulmonary arteries\nWSS reduced near tumor\ndue to vascular compression',
               (52, 68.5), (35, 70), '#cc88aa', rad=0.15)


def overlay_liver_cancer(ax):
    """Hepatocellular carcinoma — disrupted sinusoidal flow."""
    # HCC tumor mass in liver
    scatter_bed(ax, 56, 60, 3, 2.5, 250, 0.1, 2, alpha_range=(0.3,0.65),
                size_range=(2,14), seed=333, marker='s', zo=15)
    circ = Circle((56, 60), 4, facecolor='none', edgecolor='#ff4466',
                   lw=0.8, ls=':', alpha=0.6, zorder=14)
    ax.add_patch(circ)

    # Disrupted hepatic artery (increased flow to tumor)
    vessel_gradient(ax, [(55, 62), (56, 61.5), (57, 61), (57.5, 60)],
                    wss_vals=[40, 60, 80, 100], w=1.2, zo=16)

    # Portal vein compression
    vessel(ax, [(51, 49), (52.5, 52), (54, 55), (56, 58), (57, 60)],
           wss=(0.3, 2), w=1.4, zo=16, depth=0.1)

    annotation(ax, 'Hepatocellular Carcinoma\nWSS 0.1\u20132 dyne/cm\u00b2\nArterialized tumor;\ndisrupted sinusoidal\narchitecture',
               (57, 60), (65, 62), '#ff6688', edge_color='#ff4466')
    annotation(ax, 'Portal Vein Compression\nWSS reduced to 0.3\u20132\nTumor mass compresses\nvenous return',
               (54, 55), (35, 55), '#cc88aa', rad=0.1)
    annotation(ax, 'Tumor-Feeding Artery\nWSS 40\u2013100 dyne/cm\u00b2\nAberrant hypervascular\nsupply to HCC',
               (57.5, 60.5), (65, 56), '#ffaa44', edge_color='#cc8822')


def overlay_brain_tumor(ax):
    """Glioblastoma — altered cerebral hemodynamics."""
    # Tumor in brain region
    scatter_bed(ax, 50, 89, 2.5, 2, 120, 0.2, 3, alpha_range=(0.3,0.6),
                size_range=(2,12), seed=444, marker='s', zo=15)
    circ = Circle((50, 89), 3.5, facecolor='none', edgecolor='#ff4466',
                   lw=0.8, ls=':', alpha=0.6, zorder=14)
    ax.add_patch(circ)

    # Aberrant feeding vessels
    vessel_gradient(ax, [(51, 89), (51.5, 90), (52, 91)],
                    wss_vals=[10, 25, 50], w=0.6, zo=16)
    vessel_gradient(ax, [(49, 88), (49, 89.5), (49.5, 90.5)],
                    wss_vals=[10, 30, 55], w=0.6, zo=16)

    # Carotid alteration (increased flow demand)
    vessel(ax, [(50.5, 74.5), (51, 77), (51, 80), (51, 83), (51, 86), (51, 89), (51, 92)],
           wss=(15, 35), w=1.8, zo=17)

    annotation(ax, 'Glioblastoma\nWSS 0.2\u20133 dyne/cm\u00b2\nAberrant tumor neovasculature;\nblood-brain barrier disruption',
               (50, 89), (64, 92), '#ff6688', edge_color='#ff4466')
    annotation(ax, 'Carotid (Tumor Side)\nWSS 15\u201335 dyne/cm\u00b2\nIncreased flow demand\nfrom tumor angiogenesis',
               (51, 83), (64, 83), '#ccdd44', edge_color='#aacc22')


def overlay_multi_atherosclerosis(ax):
    """Multiple atherosclerotic plaque sites."""
    plaques = [
        ((51, 83), 'Carotid Bifurcation\nWSS < 4 dyne/cm\u00b2\nPrimary atherosclerosis site;\nendothelial dysfunction'),
        ((49, 77), 'Aortic Arch\nWSS < 4 dyne/cm\u00b2\nDisturbed oscillatory flow\nat branch points'),
        ((50, 42), 'Aortic Bifurcation\nWSS < 4 dyne/cm\u00b2\nIliac junction;\nrecirculation zones'),
        ((52.5, 66.5), 'Coronary Ostium\nWSS < 4 dyne/cm\u00b2\nCritical for myocardial\nperfusion'),
        ((54, 38), 'R. Iliac Bifurcation\nWSS < 4 dyne/cm\u00b2\nLower limb\natherosclerotic disease'),
        ((46, 38), 'L. Iliac Bifurcation\nWSS < 4 dyne/cm\u00b2\nPeripheral artery\ndisease risk'),
    ]

    text_positions = [
        (64, 86), (35, 79), (35, 42), (64, 66), (64, 36), (35, 36)
    ]

    for (pos, text), tpos in zip(plaques, text_positions):
        ax.plot(pos[0], pos[1], 'D', color='#ffdd33', markersize=7, zorder=20,
                markeredgecolor='white', markeredgewidth=0.5)
        circ = Circle(pos, 2, facecolor='#ffdd33', edgecolor='#ffdd33',
                       alpha=0.06, lw=0, zorder=18)
        ax.add_patch(circ)
        circ2 = Circle(pos, 2.2, facecolor='none', edgecolor='#ffdd33',
                        lw=0.6, ls='--', alpha=0.35, zorder=19)
        ax.add_patch(circ2)

        rad = 0.12 if tpos[0] > pos[0] else -0.12
        annotation(ax, text, pos, tpos, '#ffdd88', edge_color='#ffdd44', rad=rad)


def overlay_multi_stenosis(ax):
    """Multiple stenotic hotspots with extreme WSS."""
    stenoses = [
        ((51.5, 80), 'Carotid Stenosis\nWSS > 500 dyne/cm\u00b2\nTurbulent jet downstream;\nNP bilayer rupture risk'),
        ((49.5, 60), 'Renal Artery Stenosis\nWSS > 800 dyne/cm\u00b2\nRenovascular hypertension;\naltered kidney perfusion'),
        ((55, 27), 'R. Femoral Stenosis\nWSS > 400 dyne/cm\u00b2\nPeripheral artery disease;\nlimb ischemia risk'),
        ((45, 27), 'L. Femoral Stenosis\nWSS > 400 dyne/cm\u00b2\nCritical limb ischemia;\nreduced distal perfusion'),
        ((50, 48), 'Abdominal Aortic\nWSS > 600 dyne/cm\u00b2\nAneurysm-associated\nturbulence'),
    ]

    text_positions = [(64, 80), (64, 58), (64, 26), (35, 26), (35, 48)]

    for (pos, text), tpos in zip(stenoses, text_positions):
        ax.plot(pos[0], pos[1], '*', color='#ff2233', markersize=11, zorder=20,
                markeredgecolor='white', markeredgewidth=0.3)
        # Red glow ring
        circ = Circle(pos, 2, facecolor='#ff0000', edgecolor='none',
                       alpha=0.08, zorder=18)
        ax.add_patch(circ)
        circ2 = Circle(pos, 2.5, facecolor='none', edgecolor='#ff3344',
                        lw=0.7, ls=':', alpha=0.4, zorder=19)
        ax.add_patch(circ2)

        # Disturbed flow visualization (small chaotic scatter downstream)
        np.random.seed(hash(text) % 2**31)
        n_d = 30
        dx = pos[0] + np.random.normal(0, 0.8, n_d)
        dy = pos[1] - np.random.uniform(0.5, 3, n_d)  # downstream
        dw = np.random.uniform(100, 800, n_d)
        dc = CMAP(NORM(dw)); dc[:, 3] = 0.4
        ax.scatter(dx, dy, s=np.random.uniform(1, 5, n_d), c=dc, zorder=16,
                  edgecolors='none', marker='^')

        rad = 0.1 if tpos[0] > pos[0] else -0.1
        annotation(ax, text, pos, tpos, '#ff8888', edge_color='#ff4444', rad=rad)


def overlay_combined_severe(ax):
    """Combined pathology: atherosclerosis + stenosis + tumor."""
    # Atherosclerotic sites
    for pos in [(51, 83), (49, 77), (50, 42)]:
        ax.plot(pos[0], pos[1], 'D', color='#ffdd33', markersize=6, zorder=20,
                markeredgecolor='white', markeredgewidth=0.4)
        c = Circle(pos, 1.8, facecolor='none', edgecolor='#ffdd33',
                    lw=0.5, ls='--', alpha=0.3, zorder=19)
        ax.add_patch(c)

    # Stenotic sites
    for pos in [(51.5, 80), (49.5, 60)]:
        ax.plot(pos[0], pos[1], '*', color='#ff2233', markersize=9, zorder=20,
                markeredgecolor='white', markeredgewidth=0.3)
        c = Circle(pos, 1.5, facecolor='#ff0000', edgecolor='none',
                    alpha=0.06, zorder=18)
        ax.add_patch(c)

    # Lung tumor
    scatter_bed(ax, 57, 71, 2.2, 2, 100, 0.2, 3, alpha_range=(0.25,0.55),
                size_range=(2,10), seed=555, marker='s', zo=15)
    circ = Circle((57, 71), 3, facecolor='none', edgecolor='#ff4466',
                   lw=0.6, ls=':', alpha=0.5, zorder=14)
    ax.add_patch(circ)

    # Annotations (compact)
    annotation(ax, 'Carotid Plaque\n+ Stenosis\nWSS 0.5\u20134 / >500',
               (51, 82), (64, 86), '#ffdd88', edge_color='#ffdd44')
    annotation(ax, 'Aortic Arch\nPlaque\nWSS < 4',
               (49, 77), (35, 78), '#ffdd88', edge_color='#ffdd44', rad=-0.1)
    annotation(ax, 'Renal Stenosis\nWSS > 800',
               (49.5, 60), (35, 60), '#ff8888', edge_color='#ff4444', rad=0.1)
    annotation(ax, 'Lung Tumor\nWSS 0.2\u20133\nChaotic vasculature',
               (57, 71), (65, 72), '#ff6688', edge_color='#ff4466')
    annotation(ax, 'Iliac Plaque\nWSS < 4',
               (50, 42), (35, 42), '#ffdd88', edge_color='#ffdd44', rad=0.1)


# =============================================================================
# FIGURE BUILDER
# =============================================================================

SCENARIOS = {
    'healthy': {
        'title': 'Healthy Baseline',
        'subtitle': 'Normal physiological WSS distribution across the circulatory system',
        'overlay': overlay_healthy,
        'filename': '01_healthy_baseline',
    },
    'lung_cancer': {
        'title': 'Lung Cancer',
        'subtitle': 'Tumor vasculature disrupts pulmonary hemodynamics with chaotic, low-WSS regions',
        'overlay': overlay_lung_cancer,
        'filename': '02_lung_cancer',
    },
    'liver_cancer': {
        'title': 'Hepatocellular Carcinoma',
        'subtitle': 'HCC arterialization disrupts hepatic sinusoidal flow and portal hemodynamics',
        'overlay': overlay_liver_cancer,
        'filename': '03_liver_cancer_hcc',
    },
    'brain_tumor': {
        'title': 'Brain Tumor (Glioblastoma)',
        'subtitle': 'Glioblastoma neovasculature alters cerebral blood flow and carotid hemodynamics',
        'overlay': overlay_brain_tumor,
        'filename': '04_brain_tumor_gbm',
    },
    'atherosclerosis': {
        'title': 'Multi-Site Atherosclerosis',
        'subtitle': 'Plaque accumulation at multiple arterial bifurcations with low/oscillatory WSS',
        'overlay': overlay_multi_atherosclerosis,
        'filename': '05_multi_atherosclerosis',
    },
    'stenosis': {
        'title': 'Multi-Site Arterial Stenosis',
        'subtitle': 'Severe narrowing creates extreme WSS hotspots (>400\u20131000+ dyne/cm\u00b2)',
        'overlay': overlay_multi_stenosis,
        'filename': '06_multi_stenosis',
    },
    'combined': {
        'title': 'Combined Severe Pathology',
        'subtitle': 'Co-existing atherosclerosis, stenosis, and malignancy in a single patient',
        'overlay': overlay_combined_severe,
        'filename': '07_combined_pathology',
    },
}


def build_figure(scenario_key):
    """Build a single scenario figure."""
    sc = SCENARIOS[scenario_key]

    fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=BG)
    gs = gridspec.GridSpec(1, 2, width_ratios=[4, 1], wspace=0.02,
                           left=0.02, right=0.98, top=0.94, bottom=0.04)

    ax = fig.add_subplot(gs[0, 0])
    ax.set_facecolor(BG)
    ax.set_xlim(30, 72); ax.set_ylim(0, 100)
    ax.set_aspect('equal'); ax.axis('off')

    ax_r = fig.add_subplot(gs[0, 1])
    ax_r.set_facecolor(BG); ax_r.axis('off')

    # Background gradient
    grad = np.linspace(0, 1, 256).reshape(1, -1).T
    bcm = LinearSegmentedColormap.from_list('b', ['#040810', '#0c1425', '#040810'])
    ax.imshow(grad, aspect='auto', cmap=bcm, alpha=0.2, extent=[30,72,0,100], zorder=0)

    # Draw shared base
    draw_base_circulation(ax)

    # Draw scenario overlay
    sc['overlay'](ax)

    # Title
    fig.text(0.38, 0.98,
             f'Wall Shear Stress \u2014 {sc["title"]}',
             fontsize=16, color='white', ha='center', va='top',
             fontweight='bold')
    fig.text(0.38, 0.955,
             sc['subtitle'],
             fontsize=7.5, color='#7888a0', ha='center', va='top',
             fontstyle='italic')

    # Colorbar
    cb_l, cb_b, cb_w, cb_h = 0.82, 0.20, 0.022, 0.55
    ax_cb = fig.add_axes([cb_l, cb_b, cb_w, cb_h])
    ax_cb.set_facecolor('none')
    cb = ColorbarBase(ax_cb, cmap=CMAP, norm=NORM, orientation='vertical')
    cb.set_label('Wall Shear Stress (dyne/cm\u00b2)', fontsize=8, color='white', labelpad=8)
    cb.set_ticks([0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000])
    cb.set_ticklabels(['0.1', '0.5', '1', '5', '10', '50', '100', '500', '1000'])
    cb.ax.tick_params(colors='white', labelsize=6.5)
    cb.outline.set_edgecolor('#2a3548'); cb.outline.set_linewidth(0.5)

    # Colorbar annotations
    for wv, lb, cl in [(0.3,'Sinusoids','#3355aa'), (3,'Veins','#00aacc'),
                        (15,'Arteries','#66bb00'), (55,'Arterioles','#ffaa00'),
                        (400,'Stenosis','#cc0044')]:
        yn = NORM(wv)
        fig.text(cb_l+cb_w+0.03, cb_b+yn*cb_h, lb, fontsize=5, color=cl,
                 ha='left', va='center', fontweight='bold', fontstyle='italic')
        tl = Line2D([cb_l+cb_w+0.004, cb_l+cb_w+0.02],
                    [cb_b+yn*cb_h]*2, color=cl, lw=0.4, alpha=0.5,
                    transform=fig.transFigure, clip_on=False)
        fig.add_artist(tl)

    # Legend
    legs = [
        Line2D([0],[0], color=CMAP(NORM(30)), lw=3, label='Arterial (10\u201370)'),
        Line2D([0],[0], color=CMAP(NORM(3)), lw=3, label='Venous (1\u20136)'),
        Line2D([0],[0], color=CMAP(NORM(0.3)), lw=1.5, label='Lymphatic (0.1\u20130.6)'),
        Line2D([0],[0], color=CMAP(NORM(55)), lw=1, label='Arterioles (~55)'),
    ]
    # Scenario-specific legend items
    if scenario_key in ('atherosclerosis', 'combined'):
        legs.append(Line2D([0],[0], marker='D', color='w', markerfacecolor='#ffdd33',
                           markersize=5, lw=0, label='Plaque site (<4)'))
    if scenario_key in ('stenosis', 'combined'):
        legs.append(Line2D([0],[0], marker='*', color='w', markerfacecolor='#ff2233',
                           markersize=7, lw=0, label='Stenosis (>400)'))
    if scenario_key in ('lung_cancer', 'liver_cancer', 'brain_tumor', 'combined'):
        legs.append(Line2D([0],[0], marker='s', color='w', markerfacecolor='#ff4466',
                           markersize=5, lw=0, label='Tumor vasculature'))

    legs.append(Line2D([0],[0], lw=0, label=''))  # spacer
    legs.append(Line2D([0],[0], lw=0, color='#556677',
                       label='Units: dyne/cm\u00b2'))

    lg = ax.legend(handles=legs, loc='lower left', fontsize=5.5,
                    facecolor='#0c1220', edgecolor='#2a3548',
                    labelcolor='#bbccdd', framealpha=0.92,
                    borderpad=0.7, handlelength=2, handletextpad=0.5,
                    title='Vessel Type', title_fontsize=6)
    lg.get_title().set_color('#8899aa')
    lg.get_title().set_fontweight('bold')

    # Citation
    fig.text(0.5, 0.01,
             'Data: Modh et al., \u201cResolving the Biomechanical Blind Spot '
             'in Nanomedicine Translation\u201d \u2014 ACS Nano (2025)',
             fontsize=5, color='#445566', ha='center', fontstyle='italic')

    return fig


# =============================================================================
# MAIN
# =============================================================================
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Parse which scenarios to generate
    if len(sys.argv) > 1:
        keys = [k for k in sys.argv[1:] if k in SCENARIOS]
        if not keys:
            print(f"Available scenarios: {', '.join(SCENARIOS.keys())}")
            return
    else:
        keys = list(SCENARIOS.keys())

    for key in keys:
        sc = SCENARIOS[key]
        print(f'\n[{key}] Generating: {sc["title"]}...')

        fig = build_figure(key)

        png_path = os.path.join(OUT_DIR, f'{sc["filename"]}.png')
        pdf_path = os.path.join(OUT_DIR, f'{sc["filename"]}.pdf')

        print(f'  Saving PNG...')
        fig.savefig(png_path, dpi=DPI, facecolor=BG, bbox_inches='tight', pad_inches=0.1)
        print(f'  Saving PDF...')
        fig.savefig(pdf_path, facecolor=BG, bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)

        sz = os.path.getsize(png_path) / (1024*1024)
        print(f'  \u2713 {png_path} ({sz:.1f} MB)')

    print(f'\n\u2705 All scenarios saved to {OUT_DIR}/')


if __name__ == '__main__':
    main()
