#!/usr/bin/env python3
"""
Comparison Visualizations — Healthy vs Pathological WSS
========================================================

Generates professional comparison figures that make differences
between healthy and pathological states visually striking:

  1. Side-by-side panels: Healthy (left) vs Pathology (right)
     with highlighted affected regions and delta annotations
  2. Regional WSS bar charts for quantitative comparison
  3. Summary dashboard with all 7 scenarios in a grid

Usage:
    python generate_comparison.py             # all comparisons
    python generate_comparison.py dashboard   # summary grid only
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize
from matplotlib.patches import FancyBboxPatch, Circle, Ellipse, FancyArrowPatch, Rectangle
from matplotlib.lines import Line2D
from matplotlib.colorbar import ColorbarBase
from scipy.interpolate import splprep, splev
import matplotlib.gridspec as gridspec
import matplotlib.patheffects as pe
import os, sys
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIG
# =============================================================================
DPI = 300
BG = '#080c18'
OUT_DIR = '/Users/harsh/Desktop/work/1_Review Article/shear-stress-3d-viz/comparisons'

# WSS colormap (same as base)
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

# Accent colors for pathology types
TUMOR_COLOR  = '#ff3366'
PLAQUE_COLOR = '#ffcc33'
STENOSIS_COLOR = '#ff2222'
HEALTHY_COLOR = '#44dd88'

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

def vessel(ax, pts, wss, w=2.0, alpha=1.0, glow=True, depth=0.0, zo=5, n=250,
           override_color=None, dim=1.0):
    x, y = smooth(pts, n=n)
    sg = _segs(x, y)
    wss_v = np.sqrt(wss[0]*wss[1]) if isinstance(wss,(list,tuple)) else wss
    if override_color is not None:
        c = np.array(list(override_color) + [1.0]) if len(override_color) == 3 else np.array(override_color)
    else:
        c = np.array(CMAP(NORM(np.clip(wss_v, 0.08, 1500))))
    if depth > 0: c[:3] *= (1 - depth*0.55)
    c[:3] *= dim
    if glow:
        for mult, a in [(8, 0.05), (5, 0.10), (3, 0.22), (1.6, 0.40)]:
            gc = c.copy(); gc[3] = a*alpha
            ax.add_collection(LineCollection(sg, linewidths=w*mult, colors=[gc],
                              capstyle='round', zorder=zo-4))
    mc = c.copy(); mc[3] = alpha
    ax.add_collection(LineCollection(sg, linewidths=w, colors=[mc], capstyle='round', zorder=zo))
    hc = np.minimum(c[:3]*1.3+0.4, 1.0)
    hr = np.append(hc, 0.45*alpha*dim)
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


# =============================================================================
# SHARED CIRCULATORY BASE (dimming supported)
# =============================================================================
def draw_base_circulation(ax, dim=1.0):
    """Draw the complete healthy circulatory system."""
    # Veins
    vessel(ax, [(52,66),(52,62),(52,58),(52,54),(52,50),(51.5,46),(51.5,42)],
           wss=(1,6), w=3.8, zo=5, depth=0.25, dim=dim)
    vessel(ax, [(52,66),(53,69),(54,72),(54.5,74.5)],
           wss=(1,6), w=3.2, zo=5, depth=0.2, dim=dim)
    vessel(ax, [(54.5,74.5),(54.5,77),(54,80),(53.5,84),(53,87),(53,90)],
           wss=(1,6), w=1.5, zo=4, depth=0.2, dim=dim)
    vessel(ax, [(54.5,74.5),(52,76),(49,78),(47.5,81),(47,85),(47,89)],
           wss=(1,6), w=1.5, zo=4, depth=0.2, dim=dim)
    vessel(ax, [(54.5,74.5),(57,74),(60,73.5),(63,72)],
           wss=(1,6), w=1.6, zo=4, depth=0.25, dim=dim)
    vessel(ax, [(63,72),(63.5,68),(63,64),(62.5,60),(62,56),(62,52),(62,48),(62,45)],
           wss=(1,6), w=1.2, zo=4, depth=0.25, dim=dim)
    vessel(ax, [(54.5,74.5),(51,75.5),(47,75),(43,74),(40,73.5),(37,72)],
           wss=(1,6), w=1.6, zo=4, depth=0.25, dim=dim)
    vessel(ax, [(37,72),(36.5,68),(37,64),(37.5,60),(38,56),(38,52),(38,48),(38,45)],
           wss=(1,6), w=1.2, zo=4, depth=0.25, dim=dim)
    vessel(ax, [(58,60.5),(56,62),(54,63.5),(52,64.5)],
           wss=(1,6), w=1.1, zo=5, depth=0.15, dim=dim)
    vessel(ax, [(51,49),(52.5,52),(54,55),(56,58),(57,60)],
           wss=(1,6), w=1.4, zo=4, depth=0.2, dim=dim)
    vessel(ax, [(57,55),(55,55.5),(53,55.5),(52,56)],
           wss=(1,6), w=1.1, zo=4, depth=0.15, dim=dim)
    vessel(ax, [(43,55.5),(45,56),(47,56.5),(48,56.5)],
           wss=(1,6), w=1.1, zo=4, depth=0.15, dim=dim)
    vessel(ax, [(51.5,42),(53,41),(54,40),(55,39)],
           wss=(1,6), w=2.2, zo=4, depth=0.2, dim=dim)
    vessel(ax, [(55,39),(56,36),(56.5,32),(57,28),(57,24),(57,20),(56.5,16),(56.5,12),(56.5,8)],
           wss=(1,6), w=1.4, zo=4, depth=0.2, dim=dim)
    vessel(ax, [(51.5,42),(50,41),(49,40),(48,39),(47,39)],
           wss=(1,6), w=2.2, zo=4, depth=0.2, dim=dim)
    vessel(ax, [(47,39),(46,36),(45.5,32),(45,28),(45,24),(45,20),(45.5,16),(45.5,12),(45.5,8)],
           wss=(1,6), w=1.4, zo=4, depth=0.2, dim=dim)
    vessel(ax, [(56.5,68),(54.5,67.5),(53,67),(51.5,66.5)],
           wss=(1,6), w=1.3, zo=5, depth=0.1, dim=dim)
    vessel(ax, [(43.5,69),(45.5,68),(47.5,67.5),(49,67)],
           wss=(1,6), w=1.3, zo=5, depth=0.1, dim=dim)

    # Arteries
    vessel(ax, [(50,65),(50,67),(50,69.5),(50,72),(50.5,74)],
           wss=(10,70), w=4.0, zo=10, dim=dim)
    vessel(ax, [(50.5,74),(51,75.5),(50.5,76.5),(49,77),(47.5,76.5)],
           wss=(10,70), w=3.8, zo=10, dim=dim)
    vessel(ax, [(47.5,76.5),(48,74),(48.5,71),(49,68),(49.5,64),(49.5,60),
                (49.5,56),(49.5,52),(49.5,48),(49.5,44),(50,42)],
           wss=(10,70), w=3.3, zo=10, dim=dim)
    vessel(ax, [(50.5,74.5),(51,77),(51,80),(51,83),(51,86),(51,89),(51,92)],
           wss=(10,20), w=1.6, zo=9, dim=dim)
    vessel(ax, [(49,77),(48.5,79),(48.5,82),(48.5,85),(49,88),(49,91)],
           wss=(10,20), w=1.6, zo=9, dim=dim)
    vessel(ax, [(50.5,74.5),(53,75.5),(56,76),(59,75.5),(62,74.5)],
           wss=(10,70), w=2.0, zo=8, dim=dim)
    vessel(ax, [(62,74.5),(63,71),(63,67),(62.5,63),(62,59),(61.5,55),(61,51),(61,47),(61,44)],
           wss=(10,70), w=1.4, zo=8, dim=dim)
    vessel(ax, [(47.5,76.5),(45,76),(42,75.5),(39,75),(37,74.5),(35.5,73.5)],
           wss=(10,70), w=2.0, zo=8, dim=dim)
    vessel(ax, [(35.5,73.5),(36,70),(36.5,66),(37,62),(37.5,58),(38,54),(38.5,50),(39,46),(39,44)],
           wss=(10,70), w=1.4, zo=8, dim=dim)
    vessel(ax, [(50,68),(51.5,67.5),(52.5,66.5),(53,65),(52,64)],
           wss=(10,70), w=0.8, zo=11, dim=dim)
    vessel(ax, [(50,68),(48.5,67),(47.5,65.5),(48,64.5)],
           wss=(10,70), w=0.8, zo=11, dim=dim)
    vessel(ax, [(50,67.5),(52,68.5),(54,70),(56,71)],
           wss=(10,30), w=2.0, zo=7, alpha=0.85, dim=dim)
    vessel(ax, [(50,67.5),(48,69),(46,70.5),(44,71)],
           wss=(10,30), w=2.0, zo=7, alpha=0.85, dim=dim)
    vessel(ax, [(49.5,61),(51,61.5),(53,62),(55,62)],
           wss=(10,70), w=1.3, zo=9, dim=dim)
    vessel(ax, [(55,62),(57,61.5),(58.5,61)],
           wss=(10,70), w=1.0, zo=9, dim=dim)
    vessel(ax, [(49.5,61),(47.5,61),(45,60.5),(42.5,60),(41,59.5)],
           wss=(10,70), w=0.9, zo=8, dim=dim)
    vessel(ax, [(49.5,56),(51,56.5),(53,56.5),(55,56.5),(57,56)],
           wss=(10,70), w=1.3, zo=9, dim=dim)
    vessel(ax, [(49.5,57),(47.5,57),(45.5,57),(43.5,56.5)],
           wss=(10,70), w=1.3, zo=9, dim=dim)
    vessel(ax, [(49.5,54),(51,53),(53,52),(54.5,50.5)],
           wss=(10,70), w=0.8, zo=8, dim=dim)
    vessel(ax, [(49.5,51),(48,50),(46.5,49)],
           wss=(10,70), w=0.8, zo=8, dim=dim)
    vessel(ax, [(50,42),(51,41),(52,40),(53,39),(54,38)],
           wss=(10,70), w=2.4, zo=10, dim=dim)
    vessel(ax, [(54,38),(54.5,35),(55,31),(55,27),(55,23),(55,19),(55,15),(55,11),(55,7)],
           wss=(10,70), w=1.8, zo=9, dim=dim)
    vessel(ax, [(50,42),(49,41),(48,40),(47,39),(46,38)],
           wss=(10,70), w=2.4, zo=10, dim=dim)
    vessel(ax, [(46,38),(45.5,35),(45,31),(45,27),(45,23),(45,19),(45,15),(45,11),(45,7)],
           wss=(10,70), w=1.8, zo=9, dim=dim)

    # Arterioles
    vessel(ax, [(57,56),(58.5,55.5),(59.5,55)], wss=(40,60), w=0.5, zo=8, dim=dim)
    vessel(ax, [(43.5,56.5),(42,56),(41,55.5)], wss=(40,60), w=0.5, zo=8, dim=dim)
    vessel_gradient(ax, [(58.5,61),(59,60),(59.5,59),(59,58)],
                    wss_vals=[50,15,3,0.3], w=0.5, zo=9)

    # Lymphatic
    vessel(ax, [(48,42),(47.5,48),(47,54),(46.5,60),(46.5,66),(46.5,72),(47,76)],
           wss=(0.1,0.6), w=0.7, zo=3, alpha=0.65, dim=dim)
    vessel(ax, [(54,74),(55,75.5)], wss=(0.1,0.6), w=0.4, zo=3, alpha=0.55, dim=dim)

    # Microvascular beds
    scatter_bed(ax, 56, 60, 1.8, 1.5, 400, 0.1, 0.6, seed=42)
    for kx in [57.5, 42.5]:
        scatter_bed(ax, kx, 55.5, 1.0, 1.5, 100, 0.5, 8, alpha_range=(0.15,0.3),
                    size_range=(0.5,4), seed=int(kx*10), zo=2)
    for lx in [56, 44]:
        scatter_bed(ax, lx, 69.5, 2.8, 4, 150, 1, 12, alpha_range=(0.08,0.18),
                    size_range=(0.5,3), seed=int(lx*10), zo=1.5)
    scatter_bed(ax, 51, 50, 2.5, 2.5, 120, 2, 20, alpha_range=(0.08,0.15),
                size_range=(0.5,4), seed=99, zo=1.5)


# =============================================================================
# HIGHLIGHT UTILITIES
# =============================================================================
def highlight_region(ax, cx, cy, radius, color, label=None, style='ring', zo=22):
    """Draw prominent region highlight."""
    if style == 'ring':
        # Outer glow
        for r_mult, a in [(1.8, 0.06), (1.4, 0.12), (1.15, 0.18)]:
            c = Circle((cx, cy), radius*r_mult, facecolor=color, edgecolor='none',
                       alpha=a, zorder=zo-3)
            ax.add_patch(c)
        # Dashed border
        c = Circle((cx, cy), radius, facecolor='none', edgecolor=color,
                   lw=1.5, ls='--', alpha=0.8, zorder=zo)
        ax.add_patch(c)
    elif style == 'solid':
        c = Circle((cx, cy), radius, facecolor=color, edgecolor='white',
                   lw=0.8, alpha=0.15, zorder=zo-2)
        ax.add_patch(c)
        c2 = Circle((cx, cy), radius, facecolor='none', edgecolor=color,
                    lw=1.5, alpha=0.8, zorder=zo)
        ax.add_patch(c2)

    if label:
        ax.text(cx, cy - radius - 1.5, label, fontsize=6.5, color=color,
                ha='center', va='top', fontweight='bold', zorder=zo+1,
                path_effects=[pe.withStroke(linewidth=2, foreground=BG)])

def draw_delta_arrow(ax, x, y, text, color, fontsize=7, direction='right'):
    """Prominent delta WSS annotation with arrow."""
    offset = 8 if direction == 'right' else -8
    ax.annotate(text, xy=(x, y), xytext=(x+offset, y),
                fontsize=fontsize, color=color, fontweight='bold',
                ha='left' if direction == 'right' else 'right', va='center',
                arrowprops=dict(arrowstyle='->', color=color, lw=1.2,
                                connectionstyle='arc3,rad=0.08'),
                bbox=dict(boxstyle='round,pad=0.5', facecolor=BG,
                          edgecolor=color, alpha=0.95, linewidth=1.2),
                zorder=30,
                path_effects=[pe.withStroke(linewidth=0.5, foreground=BG)])


# =============================================================================
# PATHOLOGY OVERLAYS (enhanced for visibility)
# =============================================================================

def overlay_healthy_highlights(ax):
    """Subtle region labels for healthy state."""
    regions = [
        (51, 86, 'Carotid\n10-20', HEALTHY_COLOR),
        (50, 67, 'Aorta\n10-70', HEALTHY_COLOR),
        (56, 60, 'Sinusoids\n0.1-0.6', '#4488cc'),
        (50, 42, 'Iliac\n10-70', HEALTHY_COLOR),
        (55, 27, 'Femoral\n10-70', HEALTHY_COLOR),
    ]
    for x, y, label, color in regions:
        ax.text(x, y, label, fontsize=5.5, color=color, ha='center', va='center',
                fontweight='bold', alpha=0.75, zorder=25,
                path_effects=[pe.withStroke(linewidth=2.5, foreground=BG)])


def overlay_lung_cancer_enhanced(ax):
    """Lung cancer with very prominent tumor visualization."""
    # Large tumor regions with bright scatter
    scatter_bed(ax, 57, 71, 3, 3, 300, 0.2, 3, alpha_range=(0.4,0.8),
                size_range=(3,18), seed=111, marker='s', zo=15)
    scatter_bed(ax, 43, 68, 2.2, 2.5, 150, 0.3, 4, alpha_range=(0.35,0.7),
                size_range=(3,14), seed=222, marker='s', zo=15)

    # Bright highlight rings
    highlight_region(ax, 57, 71, 4.5, TUMOR_COLOR, 'R. LUNG TUMOR')
    highlight_region(ax, 43, 68, 3.5, TUMOR_COLOR, 'L. LUNG METASTASIS')

    # Tumor feeding arteries (bright, pathological)
    vessel_gradient(ax, [(54, 70), (55.5, 70.5), (56.5, 71)],
                    wss_vals=[15, 5, 1], w=1.2, zo=16)

    # Delta annotations
    draw_delta_arrow(ax, 57, 75, 'WSS: 10-30 \u2192 0.2-3\n\u0394 = -96% (tumor)', TUMOR_COLOR)
    draw_delta_arrow(ax, 43, 64, 'WSS: 10-30 \u2192 0.3-4\n\u0394 = -90% (met.)', TUMOR_COLOR, direction='left')


def overlay_liver_cancer_enhanced(ax):
    """HCC with prominent disrupted sinusoidal visualization."""
    scatter_bed(ax, 56, 60, 3.5, 3, 400, 0.05, 2, alpha_range=(0.4,0.8),
                size_range=(3,18), seed=333, marker='s', zo=15)

    highlight_region(ax, 56, 60, 5, TUMOR_COLOR, 'HEPATOCELLULAR\nCARCINOMA')

    # Arterialized tumor feeding vessel (bright orange-red)
    vessel_gradient(ax, [(55, 62), (56, 61.5), (57, 61), (57.5, 60)],
                    wss_vals=[40, 60, 80, 100], w=1.8, zo=16)

    # Compressed portal vein (dimmer, disrupted)
    vessel(ax, [(51, 49), (52.5, 52), (54, 55), (56, 58), (57, 60)],
           wss=(0.3, 2), w=1.8, zo=16, depth=0.1)

    draw_delta_arrow(ax, 57.5, 57, 'Sinusoids: 0.1-0.6 \u2192 0.05-2\nTumor arterialization\nWSS \u2191 to 100 in feeder', TUMOR_COLOR)
    draw_delta_arrow(ax, 51, 52, 'Portal vein\nWSS: 1-6 \u2192 0.3-2\nCompressed by tumor', '#ff8844', direction='left')


def overlay_brain_tumor_enhanced(ax):
    """GBM with prominent cerebral disruption."""
    scatter_bed(ax, 50, 89, 3, 2.5, 200, 0.2, 3, alpha_range=(0.4,0.8),
                size_range=(3,16), seed=444, marker='s', zo=15)

    highlight_region(ax, 50, 89, 4, TUMOR_COLOR, 'GLIOBLASTOMA')

    # Aberrant feeding vessels (bright)
    vessel_gradient(ax, [(51, 86), (51, 87.5), (51.5, 89), (52, 91)],
                    wss_vals=[15, 25, 40, 55], w=1.2, zo=16)
    vessel_gradient(ax, [(49, 86), (49, 88), (49.5, 90)],
                    wss_vals=[15, 30, 50], w=1.0, zo=16)

    # Carotid alteration highlight
    vessel(ax, [(50.5, 74.5), (51, 77), (51, 80), (51, 83), (51, 86), (51, 89), (51, 92)],
           wss=(15, 35), w=2.2, zo=17)

    draw_delta_arrow(ax, 54, 90, 'Cerebral: 10-20 \u2192 0.2-3\nWSS \u2193 96% in tumor bed\nBBB disruption', TUMOR_COLOR)
    draw_delta_arrow(ax, 54, 83, 'Carotid: 10-20 \u2192 15-35\nWSS \u2191 75% (demand)', '#ffcc44')


def overlay_atherosclerosis_enhanced(ax):
    """Multi-site atherosclerosis with prominent plaque markers."""
    plaques = [
        (51, 83, 'CAROTID\nBIFURCATION'),
        (49, 77, 'AORTIC\nARCH'),
        (50, 42, 'AORTIC\nBIFURCATION'),
        (52.5, 66.5, 'CORONARY\nOSTIUM'),
        (54, 38, 'R. ILIAC'),
        (46, 38, 'L. ILIAC'),
    ]

    for x, y, label in plaques:
        # Bright diamond marker
        ax.plot(x, y, 'D', color=PLAQUE_COLOR, markersize=10, zorder=22,
                markeredgecolor='white', markeredgewidth=0.8)
        # Glow rings
        highlight_region(ax, x, y, 2.8, PLAQUE_COLOR, style='solid')
        # Label
        ax.text(x, y + 3.5, label, fontsize=5, color=PLAQUE_COLOR,
                ha='center', va='bottom', fontweight='bold', zorder=25,
                path_effects=[pe.withStroke(linewidth=2.5, foreground=BG)])

    draw_delta_arrow(ax, 56, 85, 'All sites: WSS < 4\nOscillatory flow\nEndothelial dysfunction\n6 plaque locations', PLAQUE_COLOR)


def overlay_stenosis_enhanced(ax):
    """Multi-site stenosis with extreme WSS hotspots."""
    stenoses = [
        (51.5, 80, 'CAROTID\nSTENOSIS', '>500'),
        (49.5, 60, 'RENAL\nSTENOSIS', '>800'),
        (55, 27, 'R. FEMORAL\nSTENOSIS', '>400'),
        (45, 27, 'L. FEMORAL\nSTENOSIS', '>400'),
        (50, 48, 'ABDOMINAL\nAORTIC', '>600'),
    ]

    for x, y, label, wss_txt in stenoses:
        # Bright red star
        ax.plot(x, y, '*', color=STENOSIS_COLOR, markersize=16, zorder=22,
                markeredgecolor='white', markeredgewidth=0.5)
        # Pulsing glow rings
        for r, a in [(3.5, 0.08), (2.5, 0.15), (1.5, 0.22)]:
            c = Circle((x, y), r, facecolor=STENOSIS_COLOR, edgecolor='none',
                       alpha=a, zorder=20)
            ax.add_patch(c)
        # Turbulence scatter downstream
        np.random.seed(hash(label) % 2**31)
        n_t = 50
        dx = x + np.random.normal(0, 1.0, n_t)
        dy = y - np.random.uniform(0.5, 4, n_t)
        dw = np.random.uniform(200, 1000, n_t)
        dc = CMAP(NORM(dw)); dc[:, 3] = 0.6
        ax.scatter(dx, dy, s=np.random.uniform(2, 8, n_t), c=dc, zorder=18,
                  edgecolors='none', marker='^')
        # Label + WSS
        ax.text(x, y + 3, f'{label}\nWSS {wss_txt}', fontsize=5, color=STENOSIS_COLOR,
                ha='center', va='bottom', fontweight='bold', zorder=25,
                path_effects=[pe.withStroke(linewidth=2.5, foreground=BG)])

    draw_delta_arrow(ax, 56, 60, 'Normal: 10-70\n\u2192 Stenotic: 400-1000+\nWSS \u2191 10-50\u00d7\nBilayer rupture risk', STENOSIS_COLOR)


def overlay_combined_enhanced(ax):
    """Combined pathology with all markers."""
    # Atherosclerotic sites
    for x, y in [(51, 83), (49, 77), (50, 42)]:
        ax.plot(x, y, 'D', color=PLAQUE_COLOR, markersize=8, zorder=22,
                markeredgecolor='white', markeredgewidth=0.6)
        highlight_region(ax, x, y, 2, PLAQUE_COLOR, style='solid')

    # Stenotic sites
    for x, y in [(51.5, 80), (49.5, 60)]:
        ax.plot(x, y, '*', color=STENOSIS_COLOR, markersize=14, zorder=22,
                markeredgecolor='white', markeredgewidth=0.5)
        for r, a in [(2.5, 0.1), (1.5, 0.2)]:
            c = Circle((x, y), r, facecolor=STENOSIS_COLOR, edgecolor='none',
                       alpha=a, zorder=20)
            ax.add_patch(c)

    # Lung tumor
    scatter_bed(ax, 57, 71, 2.5, 2.5, 200, 0.2, 3, alpha_range=(0.4,0.7),
                size_range=(3,14), seed=555, marker='s', zo=15)
    highlight_region(ax, 57, 71, 3.5, TUMOR_COLOR)

    # Legend annotations
    draw_delta_arrow(ax, 57, 75, 'TUMOR\nWSS 0.2-3', TUMOR_COLOR)
    draw_delta_arrow(ax, 55, 83, 'PLAQUE\nWSS < 4', PLAQUE_COLOR)
    draw_delta_arrow(ax, 55, 60, 'STENOSIS\nWSS > 800', STENOSIS_COLOR)


# =============================================================================
# REGIONAL WSS BAR CHART
# =============================================================================
def draw_wss_bar_chart(ax, scenario_key):
    """Draw horizontal bar chart comparing healthy vs pathological WSS."""
    ax.set_facecolor('#0a0f1c')

    # Healthy WSS ranges (geometric mean for plotting)
    healthy = {
        'Carotid': 14.1,    # sqrt(10*20)
        'Aorta': 26.5,      # sqrt(10*70)
        'Coronary': 26.5,
        'Pulmonary': 17.3,  # sqrt(10*30)
        'Hepatic Sin.': 0.24,  # sqrt(0.1*0.6)
        'Renal Art.': 26.5,
        'Femoral': 26.5,
        'Iliac': 26.5,
        'Venous': 2.45,     # sqrt(1*6)
    }

    # Pathological WSS by scenario
    pathological = {
        'lung_cancer': {
            'Carotid': 14.1, 'Aorta': 26.5, 'Coronary': 26.5,
            'Pulmonary': 1.5, 'Hepatic Sin.': 0.24, 'Renal Art.': 26.5,
            'Femoral': 26.5, 'Iliac': 26.5, 'Venous': 2.45,
        },
        'liver_cancer': {
            'Carotid': 14.1, 'Aorta': 26.5, 'Coronary': 26.5,
            'Pulmonary': 17.3, 'Hepatic Sin.': 0.45, 'Renal Art.': 26.5,
            'Femoral': 26.5, 'Iliac': 26.5, 'Venous': 2.45,
        },
        'brain_tumor': {
            'Carotid': 22.9, 'Aorta': 26.5, 'Coronary': 26.5,
            'Pulmonary': 17.3, 'Hepatic Sin.': 0.24, 'Renal Art.': 26.5,
            'Femoral': 26.5, 'Iliac': 26.5, 'Venous': 2.45,
        },
        'atherosclerosis': {
            'Carotid': 2.0, 'Aorta': 2.0, 'Coronary': 2.0,
            'Pulmonary': 17.3, 'Hepatic Sin.': 0.24, 'Renal Art.': 26.5,
            'Femoral': 26.5, 'Iliac': 2.0, 'Venous': 2.45,
        },
        'stenosis': {
            'Carotid': 500, 'Aorta': 600, 'Coronary': 26.5,
            'Pulmonary': 17.3, 'Hepatic Sin.': 0.24, 'Renal Art.': 800,
            'Femoral': 400, 'Iliac': 26.5, 'Venous': 2.45,
        },
        'combined': {
            'Carotid': 250, 'Aorta': 3.0, 'Coronary': 2.0,
            'Pulmonary': 1.5, 'Hepatic Sin.': 0.24, 'Renal Art.': 800,
            'Femoral': 26.5, 'Iliac': 2.0, 'Venous': 2.45,
        },
    }

    if scenario_key == 'healthy' or scenario_key not in pathological:
        # Just show healthy bars
        regions = list(healthy.keys())
        vals = list(healthy.values())
        colors = [CMAP(NORM(v)) for v in vals]
        y_pos = np.arange(len(regions))
        bars = ax.barh(y_pos, vals, height=0.6, color=colors, edgecolor='white',
                       linewidth=0.3, alpha=0.9)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(regions, fontsize=7, color='#bbccdd')
        ax.set_xscale('log')
        ax.set_xlim(0.05, 1500)
        ax.set_xlabel('WSS (dyne/cm\u00b2)', fontsize=8, color='#aabbcc')
        ax.tick_params(axis='x', colors='#778899', labelsize=6)
        ax.set_title('Healthy WSS Distribution', fontsize=9, color='white',
                     fontweight='bold', pad=8)
        ax.spines['bottom'].set_color('#2a3548'); ax.spines['left'].set_color('#2a3548')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        return

    path_vals = pathological[scenario_key]
    regions = list(healthy.keys())
    h_vals = [healthy[r] for r in regions]
    p_vals = [path_vals.get(r, healthy[r]) for r in regions]

    y_pos = np.arange(len(regions))
    bar_h = 0.35

    # Healthy bars (dimmer)
    h_colors = [(*CMAP(NORM(v))[:3], 0.45) for v in h_vals]
    ax.barh(y_pos + bar_h/2, h_vals, height=bar_h, color=h_colors,
            edgecolor='#446688', linewidth=0.4, label='Healthy')

    # Pathological bars (bright)
    p_colors = []
    for hv, pv in zip(h_vals, p_vals):
        if pv > hv * 1.5:  # increased
            p_colors.append((*_h2r('#ff4444'), 0.9))
        elif pv < hv * 0.5:  # decreased
            p_colors.append((*_h2r('#4488ff'), 0.9))
        else:
            p_colors.append((*CMAP(NORM(pv))[:3], 0.9))

    ax.barh(y_pos - bar_h/2, p_vals, height=bar_h, color=p_colors,
            edgecolor='white', linewidth=0.5, label='Pathological')

    # Delta labels
    for i, (hv, pv) in enumerate(zip(h_vals, p_vals)):
        if abs(pv - hv) / max(hv, 0.01) > 0.3:
            ratio = pv / hv if hv > 0 else 0
            if ratio > 1:
                label = f'\u2191{ratio:.0f}\u00d7' if ratio > 2 else f'\u2191{(ratio-1)*100:.0f}%'
                color = '#ff6666'
            else:
                label = f'\u2193{(1-ratio)*100:.0f}%'
                color = '#66aaff'
            x_pos = max(pv, hv) * 1.3
            ax.text(x_pos, i, label, fontsize=6.5, color=color, va='center',
                    fontweight='bold',
                    path_effects=[pe.withStroke(linewidth=1.5, foreground=BG)])

    ax.set_yticks(y_pos)
    ax.set_yticklabels(regions, fontsize=7, color='#bbccdd')
    ax.set_xscale('log')
    ax.set_xlim(0.05, 1500)
    ax.set_xlabel('WSS (dyne/cm\u00b2)', fontsize=8, color='#aabbcc')
    ax.tick_params(axis='x', colors='#778899', labelsize=6)
    ax.tick_params(axis='y', colors='#778899')

    # Legend
    from matplotlib.patches import Patch
    leg_items = [
        Patch(facecolor='#446688', edgecolor='#446688', alpha=0.5, label='Healthy'),
        Patch(facecolor='#ff4444', alpha=0.7, label='Pathological (\u2191)'),
        Patch(facecolor='#4488ff', alpha=0.7, label='Pathological (\u2193)'),
    ]
    ax.legend(handles=leg_items, fontsize=6, facecolor='#0c1220',
              edgecolor='#2a3548', labelcolor='#aabbcc', loc='lower right')

    ax.spines['bottom'].set_color('#2a3548'); ax.spines['left'].set_color('#2a3548')
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)


# =============================================================================
# SIDE-BY-SIDE COMPARISON FIGURE
# =============================================================================
SCENARIOS = {
    'lung_cancer': {
        'title': 'Lung Cancer',
        'subtitle': 'Tumor vasculature disrupts pulmonary hemodynamics',
        'overlay': overlay_lung_cancer_enhanced,
        'filename': 'compare_lung_cancer',
    },
    'liver_cancer': {
        'title': 'Hepatocellular Carcinoma',
        'subtitle': 'HCC arterialization disrupts hepatic sinusoidal flow',
        'overlay': overlay_liver_cancer_enhanced,
        'filename': 'compare_liver_cancer',
    },
    'brain_tumor': {
        'title': 'Brain Tumor (Glioblastoma)',
        'subtitle': 'Neovasculature alters cerebral blood flow',
        'overlay': overlay_brain_tumor_enhanced,
        'filename': 'compare_brain_tumor',
    },
    'atherosclerosis': {
        'title': 'Multi-Site Atherosclerosis',
        'subtitle': 'Plaque at multiple arterial bifurcations (low WSS)',
        'overlay': overlay_atherosclerosis_enhanced,
        'filename': 'compare_atherosclerosis',
    },
    'stenosis': {
        'title': 'Multi-Site Arterial Stenosis',
        'subtitle': 'Extreme WSS hotspots from severe narrowing',
        'overlay': overlay_stenosis_enhanced,
        'filename': 'compare_stenosis',
    },
    'combined': {
        'title': 'Combined Severe Pathology',
        'subtitle': 'Atherosclerosis + stenosis + malignancy',
        'overlay': overlay_combined_enhanced,
        'filename': 'compare_combined',
    },
}


def build_comparison(scenario_key):
    """Build side-by-side comparison: Healthy (left) vs Pathology (right) + bar chart."""
    sc = SCENARIOS[scenario_key]

    fig = plt.figure(figsize=(22, 14), facecolor=BG)
    gs = gridspec.GridSpec(2, 3, width_ratios=[2, 2, 1.4],
                           height_ratios=[6, 1.2],
                           hspace=0.08, wspace=0.04,
                           left=0.02, right=0.98, top=0.93, bottom=0.04)

    # ── LEFT: Healthy ──
    ax_h = fig.add_subplot(gs[0, 0])
    ax_h.set_facecolor(BG)
    ax_h.set_xlim(30, 72); ax_h.set_ylim(0, 100)
    ax_h.set_aspect('equal'); ax_h.axis('off')
    grad = np.linspace(0, 1, 256).reshape(1, -1).T
    bcm = LinearSegmentedColormap.from_list('b', ['#040810', '#0c1425', '#040810'])
    ax_h.imshow(grad, aspect='auto', cmap=bcm, alpha=0.2, extent=[30,72,0,100], zorder=0)
    draw_base_circulation(ax_h)
    overlay_healthy_highlights(ax_h)
    ax_h.text(51, 98, 'HEALTHY', fontsize=14, color=HEALTHY_COLOR, ha='center',
              va='top', fontweight='bold',
              path_effects=[pe.withStroke(linewidth=3, foreground=BG)])
    ax_h.text(51, 95.5, 'Normal physiological WSS', fontsize=7, color='#7888a0',
              ha='center', va='top', fontstyle='italic')
    # Border
    rect = Rectangle((30.5, 0.5), 41, 99, linewidth=1.5, edgecolor=HEALTHY_COLOR,
                      facecolor='none', alpha=0.3, zorder=30)
    ax_h.add_patch(rect)

    # ── RIGHT: Pathology ──
    ax_p = fig.add_subplot(gs[0, 1])
    ax_p.set_facecolor(BG)
    ax_p.set_xlim(30, 72); ax_p.set_ylim(0, 100)
    ax_p.set_aspect('equal'); ax_p.axis('off')
    ax_p.imshow(grad, aspect='auto', cmap=bcm, alpha=0.2, extent=[30,72,0,100], zorder=0)
    draw_base_circulation(ax_p, dim=0.5)  # Dim the base
    sc['overlay'](ax_p)  # Bright pathology overlay

    pathology_color = TUMOR_COLOR if scenario_key in ('lung_cancer','liver_cancer','brain_tumor','combined') else \
                      PLAQUE_COLOR if scenario_key == 'atherosclerosis' else STENOSIS_COLOR
    ax_p.text(51, 98, sc['title'].upper(), fontsize=14, color=pathology_color, ha='center',
              va='top', fontweight='bold',
              path_effects=[pe.withStroke(linewidth=3, foreground=BG)])
    ax_p.text(51, 95.5, sc['subtitle'], fontsize=7, color='#7888a0',
              ha='center', va='top', fontstyle='italic')
    rect2 = Rectangle((30.5, 0.5), 41, 99, linewidth=1.5, edgecolor=pathology_color,
                       facecolor='none', alpha=0.3, zorder=30)
    ax_p.add_patch(rect2)

    # ── BAR CHART (right column) ──
    ax_bar = fig.add_subplot(gs[0, 2])
    ax_bar.set_facecolor('#0a0f1c')
    draw_wss_bar_chart(ax_bar, scenario_key)
    ax_bar.set_title(f'WSS Comparison\nHealthy vs {sc["title"]}', fontsize=9,
                     color='white', fontweight='bold', pad=10)

    # ── COLORBAR (bottom row, spanning all columns) ──
    ax_cb_row = fig.add_subplot(gs[1, :])
    ax_cb_row.set_facecolor(BG); ax_cb_row.axis('off')

    cb_l, cb_b, cb_w, cb_h = 0.15, 0.06, 0.50, 0.018
    ax_cb = fig.add_axes([cb_l, cb_b, cb_w, cb_h])
    ax_cb.set_facecolor('none')
    cb = ColorbarBase(ax_cb, cmap=CMAP, norm=NORM, orientation='horizontal')
    cb.set_label('Wall Shear Stress (dyne/cm\u00b2)', fontsize=8, color='white', labelpad=6)
    cb.set_ticks([0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000])
    cb.set_ticklabels(['0.1', '0.5', '1', '5', '10', '50', '100', '500', '1000'])
    cb.ax.tick_params(colors='white', labelsize=7)
    cb.outline.set_edgecolor('#2a3548'); cb.outline.set_linewidth(0.5)

    # Legend at bottom
    legs = [
        Line2D([0],[0], color=CMAP(NORM(30)), lw=3, label='Arterial (10-70)'),
        Line2D([0],[0], color=CMAP(NORM(3)), lw=3, label='Venous (1-6)'),
        Line2D([0],[0], color=CMAP(NORM(0.3)), lw=1.5, label='Lymphatic (0.1-0.6)'),
        Line2D([0],[0], marker='D', color='w', markerfacecolor=PLAQUE_COLOR, markersize=6, lw=0, label='Plaque site'),
        Line2D([0],[0], marker='*', color='w', markerfacecolor=STENOSIS_COLOR, markersize=8, lw=0, label='Stenosis'),
        Line2D([0],[0], marker='s', color='w', markerfacecolor=TUMOR_COLOR, markersize=5, lw=0, label='Tumor'),
    ]
    fig.legend(handles=legs, loc='lower right', fontsize=7, ncol=3,
               facecolor='#0c1220', edgecolor='#2a3548', labelcolor='#bbccdd',
               framealpha=0.92, bbox_to_anchor=(0.97, 0.01))

    # Super-title
    fig.text(0.5, 0.975,
             f'Wall Shear Stress Comparison \u2014 {sc["title"]}',
             fontsize=18, color='white', ha='center', va='top', fontweight='bold')

    # Citation
    fig.text(0.5, 0.01,
             'Data: Modh et al., "Resolving the Biomechanical Blind Spot in Nanomedicine Translation" \u2014 ACS Nano (2025)',
             fontsize=5.5, color='#445566', ha='center', fontstyle='italic')

    return fig


# =============================================================================
# SUMMARY DASHBOARD (all scenarios in grid)
# =============================================================================
def build_dashboard():
    """Build a summary grid with all 7 scenarios as thumbnail panels."""
    fig = plt.figure(figsize=(28, 16), facecolor=BG)
    gs = gridspec.GridSpec(2, 4, hspace=0.12, wspace=0.06,
                           left=0.02, right=0.98, top=0.92, bottom=0.06)

    all_scenarios = [
        ('healthy', 'Healthy Baseline', overlay_healthy_highlights, HEALTHY_COLOR),
        ('lung_cancer', 'Lung Cancer', overlay_lung_cancer_enhanced, TUMOR_COLOR),
        ('liver_cancer', 'Hepatocellular Carcinoma', overlay_liver_cancer_enhanced, TUMOR_COLOR),
        ('brain_tumor', 'Brain Tumor (GBM)', overlay_brain_tumor_enhanced, TUMOR_COLOR),
        ('atherosclerosis', 'Multi-Site Atherosclerosis', overlay_atherosclerosis_enhanced, PLAQUE_COLOR),
        ('stenosis', 'Multi-Site Stenosis', overlay_stenosis_enhanced, STENOSIS_COLOR),
        ('combined', 'Combined Pathology', overlay_combined_enhanced, TUMOR_COLOR),
    ]

    positions = [(0,0), (0,1), (0,2), (0,3), (1,0), (1,1), (1,2)]

    for (key, title, overlay_fn, color), (row, col) in zip(all_scenarios, positions):
        ax = fig.add_subplot(gs[row, col])
        ax.set_facecolor(BG)
        ax.set_xlim(30, 72); ax.set_ylim(0, 100)
        ax.set_aspect('equal'); ax.axis('off')

        grad = np.linspace(0, 1, 256).reshape(1, -1).T
        bcm = LinearSegmentedColormap.from_list('b', ['#040810', '#0c1425', '#040810'])
        ax.imshow(grad, aspect='auto', cmap=bcm, alpha=0.15, extent=[30,72,0,100], zorder=0)

        dim = 1.0 if key == 'healthy' else 0.45
        draw_base_circulation(ax, dim=dim)
        overlay_fn(ax)

        # Title + border
        ax.text(51, 99, title.upper(), fontsize=9, color=color, ha='center',
                va='top', fontweight='bold',
                path_effects=[pe.withStroke(linewidth=2.5, foreground=BG)])
        rect = Rectangle((30.5, 0.5), 41, 99, linewidth=2, edgecolor=color,
                          facecolor='none', alpha=0.4, zorder=30)
        ax.add_patch(rect)

    # Last cell (1,3) — colorbar + legend
    ax_info = fig.add_subplot(gs[1, 3])
    ax_info.set_facecolor('#0a0f1c')
    ax_info.axis('off')

    # Colorbar inside info panel
    cb_l2, cb_b2, cb_w2, cb_h2 = 0.775, 0.15, 0.018, 0.35
    ax_cb2 = fig.add_axes([cb_l2, cb_b2, cb_w2, cb_h2])
    cb2 = ColorbarBase(ax_cb2, cmap=CMAP, norm=NORM, orientation='vertical')
    cb2.set_label('WSS (dyne/cm\u00b2)', fontsize=7, color='white', labelpad=6)
    cb2.set_ticks([0.1, 1, 10, 100, 1000])
    cb2.set_ticklabels(['0.1', '1', '10', '100', '1000'])
    cb2.ax.tick_params(colors='white', labelsize=6)
    cb2.outline.set_edgecolor('#2a3548')

    # Legend
    legs = [
        Line2D([0],[0], color=HEALTHY_COLOR, lw=0, marker='o', markersize=8, label='Healthy'),
        Line2D([0],[0], color=TUMOR_COLOR, lw=0, marker='s', markersize=7, label='Tumor vasculature'),
        Line2D([0],[0], color=PLAQUE_COLOR, lw=0, marker='D', markersize=7, label='Atherosclerotic plaque'),
        Line2D([0],[0], color=STENOSIS_COLOR, lw=0, marker='*', markersize=9, label='Stenosis hotspot'),
    ]
    ax_info.legend(handles=legs, loc='center right', fontsize=7,
                    facecolor='#0c1220', edgecolor='#2a3548', labelcolor='#bbccdd',
                    framealpha=0.92, bbox_to_anchor=(0.95, 0.7))

    # Info text
    ax_info.text(0.5, 0.3,
                 'Color intensity = WSS magnitude\n'
                 'Logarithmic scale: 0.1\u20131000+ dyne/cm\u00b2\n\n'
                 'Dim vessels = unchanged baseline\n'
                 'Bright overlays = pathological changes',
                 fontsize=7, color='#7888a0', ha='center', va='center',
                 transform=ax_info.transAxes, fontstyle='italic',
                 bbox=dict(boxstyle='round,pad=0.8', facecolor='#0c1220',
                           edgecolor='#2a3548', alpha=0.9))

    # Super title
    fig.text(0.5, 0.975,
             'Wall Shear Stress \u2014 Pathological Scenario Comparison Dashboard',
             fontsize=20, color='white', ha='center', va='top', fontweight='bold')
    fig.text(0.5, 0.945,
             'How disease reshapes the hemodynamic landscape for nanocarrier delivery',
             fontsize=10, color='#7888a0', ha='center', va='top', fontstyle='italic')

    fig.text(0.5, 0.015,
             'Data: Modh et al., "Resolving the Biomechanical Blind Spot in Nanomedicine Translation" \u2014 ACS Nano (2025)',
             fontsize=6, color='#445566', ha='center', fontstyle='italic')

    return fig


# =============================================================================
# MAIN
# =============================================================================
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    if len(sys.argv) > 1 and sys.argv[1] == 'dashboard':
        keys = []
    elif len(sys.argv) > 1:
        keys = [k for k in sys.argv[1:] if k in SCENARIOS]
    else:
        keys = list(SCENARIOS.keys())

    # Generate individual comparison figures
    for key in keys:
        sc = SCENARIOS[key]
        print(f'\n[{key}] Generating comparison: Healthy vs {sc["title"]}...')
        fig = build_comparison(key)
        png = os.path.join(OUT_DIR, f'{sc["filename"]}.png')
        pdf = os.path.join(OUT_DIR, f'{sc["filename"]}.pdf')
        fig.savefig(png, dpi=DPI, facecolor=BG, bbox_inches='tight', pad_inches=0.1)
        fig.savefig(pdf, facecolor=BG, bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)
        sz = os.path.getsize(png) / (1024*1024)
        print(f'  \u2713 {png} ({sz:.1f} MB)')

    # Always generate the dashboard
    print(f'\n[dashboard] Generating scenario comparison dashboard...')
    fig = build_dashboard()
    png = os.path.join(OUT_DIR, 'scenario_dashboard.png')
    pdf = os.path.join(OUT_DIR, 'scenario_dashboard.pdf')
    fig.savefig(png, dpi=DPI, facecolor=BG, bbox_inches='tight', pad_inches=0.1)
    fig.savefig(pdf, facecolor=BG, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)
    sz = os.path.getsize(png) / (1024*1024)
    print(f'  \u2713 {png} ({sz:.1f} MB)')

    print(f'\n\u2705 All comparisons saved to {OUT_DIR}/')


if __name__ == '__main__':
    main()
