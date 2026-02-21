#!/usr/bin/env python3
"""
Professional 2D Illustration of Wall Shear Stress in the Human Circulatory System
===================================================================================

Creates a publication-quality figure with:
- Detailed anatomical vessel paths (bezier curves)
- 3D depth effect via gradient shading, shadows, and glow
- Logarithmic WSS color mapping with smooth vessel gradients
- Semi-transparent human body silhouette with organ outlines
- Professional annotations, colorbar, and legend

Output: High-resolution PNG (300 DPI) suitable for journal figures

Data source: "Resolving the Biomechanical Blind Spot in Nanomedicine Translation"
             Modh et al., ACS Nano (2025)
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize
from matplotlib.patches import FancyBboxPatch, Circle, Ellipse, FancyArrowPatch
from matplotlib.lines import Line2D
from scipy.interpolate import splprep, splev
import matplotlib.gridspec as gridspec
from matplotlib.colorbar import ColorbarBase
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURATION
# =============================================================================

DPI = 300
FIG_WIDTH = 14     # inches
FIG_HEIGHT = 20    # inches

# Body coordinate system (arbitrary units, head top = 100, feet = 0)
BODY_TOP = 98
BODY_BOT = 2

# Background
BG_COLOR = '#0a0e1a'
BG_GRADIENT_TOP = '#0f1628'
BG_GRADIENT_BOT = '#060a14'

# WSS colormap: deep blue → cyan → green → yellow → orange → red → magenta
WSS_COLORS = [
    (0.00, '#0a1a6e'),   # 0.1 dyne/cm² — deep indigo
    (0.15, '#0055cc'),   # 0.5 — royal blue
    (0.25, '#00aadd'),   # 1 — cyan
    (0.35, '#00cc88'),   # 3 — teal-green
    (0.50, '#44dd00'),   # 10 — lime
    (0.60, '#ccdd00'),   # 20 — yellow-green
    (0.70, '#ffaa00'),   # 50 — orange
    (0.80, '#ff4400'),   # 100 — red-orange
    (0.90, '#dd0044'),   # 300 — crimson
    (1.00, '#aa00cc'),   # 1000 — purple
]

def create_wss_cmap():
    """Create the custom WSS colormap."""
    positions = [c[0] for c in WSS_COLORS]
    colors_hex = [c[1] for c in WSS_COLORS]
    colors_rgb = []
    for h in colors_hex:
        h = h.lstrip('#')
        colors_rgb.append(tuple(int(h[i:i+2], 16)/255.0 for i in (0, 2, 4)))

    cdict = {'red': [], 'green': [], 'blue': []}
    for pos, (r, g, b) in zip(positions, colors_rgb):
        cdict['red'].append((pos, r, r))
        cdict['green'].append((pos, g, g))
        cdict['blue'].append((pos, b, b))

    return LinearSegmentedColormap('wss_cmap', cdict, N=512)

WSS_CMAP = create_wss_cmap()
WSS_NORM = LogNorm(vmin=0.1, vmax=1200)


# =============================================================================
# SMOOTH CURVE UTILITIES
# =============================================================================

def smooth_curve(points, n=200, smooth=0.0):
    """Create a smooth cubic spline through control points."""
    pts = np.array(points)
    if len(pts) < 3:
        # Linear interpolation for 2-point paths
        t = np.linspace(0, 1, n)
        x = pts[0, 0] + t * (pts[-1, 0] - pts[0, 0])
        y = pts[0, 1] + t * (pts[-1, 1] - pts[0, 1])
        return x, y

    try:
        tck, u = splprep([pts[:, 0], pts[:, 1]], s=smooth, k=min(3, len(pts)-1))
        t_new = np.linspace(0, 1, n)
        x_new, y_new = splev(t_new, tck)
        return np.array(x_new), np.array(y_new)
    except Exception:
        t = np.linspace(0, 1, n)
        x = np.interp(t, np.linspace(0, 1, len(pts)), pts[:, 0])
        y = np.interp(t, np.linspace(0, 1, len(pts)), pts[:, 1])
        return x, y


def draw_vessel(ax, points, wss, width=2.0, alpha=1.0, glow=True,
                depth_fade=0.0, zorder=5, label=None, n_pts=200):
    """
    Draw a vessel with WSS color gradient and 3D depth effects.

    Args:
        ax: Matplotlib axes
        points: Control points [(x,y), ...]
        wss: WSS value or (min, max) tuple
        width: Vessel line width
        alpha: Base opacity
        glow: Add glow effect for 3D depth
        depth_fade: 0-1, how much to darken (simulates depth)
        zorder: Drawing order
        label: Optional label
        n_pts: Interpolation points
    """
    x, y = smooth_curve(points, n=n_pts)

    # Get WSS color
    if isinstance(wss, (list, tuple)):
        wss_val = np.sqrt(wss[0] * wss[1])  # geometric mean
    else:
        wss_val = wss

    base_color = np.array(WSS_CMAP(WSS_NORM(wss_val)))

    # Apply depth fade (darken for "behind" vessels)
    if depth_fade > 0:
        base_color[:3] *= (1 - depth_fade * 0.6)

    # Create line segments for gradient rendering
    points_arr = np.column_stack([x, y])
    segments = np.array([points_arr[:-1], points_arr[1:]]).transpose(1, 0, 2)

    # ── GLOW LAYER (3D depth effect) ──
    if glow:
        # Outer glow — wide, very transparent
        glow_color = base_color.copy()
        glow_color[3] = 0.08 * alpha
        lc_glow3 = LineCollection(segments, linewidths=width * 5.0,
                                   colors=[glow_color], capstyle='round',
                                   zorder=zorder - 3)
        ax.add_collection(lc_glow3)

        # Mid glow
        glow_color2 = base_color.copy()
        glow_color2[3] = 0.15 * alpha
        lc_glow2 = LineCollection(segments, linewidths=width * 3.0,
                                   colors=[glow_color2], capstyle='round',
                                   zorder=zorder - 2)
        ax.add_collection(lc_glow2)

        # Inner glow
        glow_color3 = base_color.copy()
        glow_color3[3] = 0.3 * alpha
        lc_glow1 = LineCollection(segments, linewidths=width * 1.8,
                                   colors=[glow_color3], capstyle='round',
                                   zorder=zorder - 1)
        ax.add_collection(lc_glow1)

    # ── MAIN VESSEL ──
    main_color = base_color.copy()
    main_color[3] = alpha
    lc_main = LineCollection(segments, linewidths=width,
                              colors=[main_color], capstyle='round',
                              zorder=zorder)
    ax.add_collection(lc_main)

    # ── SPECULAR HIGHLIGHT (3D tube effect) ──
    highlight_color = np.minimum(base_color[:3] * 1.5 + 0.3, 1.0)
    highlight_rgba = np.append(highlight_color, 0.35 * alpha)
    lc_highlight = LineCollection(segments, linewidths=width * 0.3,
                                   colors=[highlight_rgba], capstyle='round',
                                   zorder=zorder + 1)
    ax.add_collection(lc_highlight)


def draw_vessel_varying_wss(ax, points, wss_values, width=2.0, alpha=1.0,
                             glow=True, zorder=5, n_pts=200):
    """
    Draw a vessel with spatially varying WSS (color changes along path).

    Args:
        points: Control points
        wss_values: List of WSS values corresponding to positions along the vessel
    """
    x, y = smooth_curve(points, n=n_pts)
    points_arr = np.column_stack([x, y])
    segments = np.array([points_arr[:-1], points_arr[1:]]).transpose(1, 0, 2)

    # Interpolate WSS values along the vessel
    t_wss = np.linspace(0, 1, len(wss_values))
    t_seg = np.linspace(0, 1, len(segments))
    wss_interp = np.interp(t_seg, t_wss, wss_values)

    # Get colors for each segment
    colors = WSS_CMAP(WSS_NORM(np.clip(wss_interp, 0.1, 1200)))
    colors[:, 3] = alpha

    if glow:
        glow_colors = colors.copy()
        glow_colors[:, 3] = 0.1 * alpha
        lc_g = LineCollection(segments, linewidths=width * 4, colors=glow_colors,
                               capstyle='round', zorder=zorder - 2)
        ax.add_collection(lc_g)

        glow_colors2 = colors.copy()
        glow_colors2[:, 3] = 0.25 * alpha
        lc_g2 = LineCollection(segments, linewidths=width * 2, colors=glow_colors2,
                                capstyle='round', zorder=zorder - 1)
        ax.add_collection(lc_g2)

    lc = LineCollection(segments, linewidths=width, colors=colors,
                         capstyle='round', zorder=zorder)
    ax.add_collection(lc)

    # Highlight
    h_colors = np.minimum(colors[:, :3] * 1.4 + 0.25, 1.0)
    h_rgba = np.column_stack([h_colors, np.full(len(h_colors), 0.3 * alpha)])
    lc_h = LineCollection(segments, linewidths=width * 0.3, colors=h_rgba,
                           capstyle='round', zorder=zorder + 1)
    ax.add_collection(lc_h)


# =============================================================================
# BODY SILHOUETTE
# =============================================================================

def draw_body_silhouette(ax):
    """Draw a detailed, semi-transparent human body outline with organ shapes."""

    # ── BODY OUTLINE (smooth silhouette) ──
    # Right side of body (mirrored for left)
    right_outline = [
        (50, 95),   # top of head
        (54, 93),   # head right
        (55, 89),   # temple
        (54.5, 85), # jaw
        (52, 83),   # chin area
        (53, 81),   # neck
        (54, 79),   # neck base
        (60, 77),   # shoulder top
        (64, 76),   # shoulder outer
        (65, 74),   # deltoid
        (64, 70),   # upper arm
        (63.5, 65), # mid arm
        (63, 60),   # elbow area
        (62, 55),   # forearm
        (61.5, 50), # lower forearm
        (61, 46),   # wrist area
        (62, 44),   # hand
        (62.5, 42), # fingers
    ]

    left_outline = [(100 - x, y) for x, y in right_outline][::-1]

    # Torso right
    torso_right = [
        (64, 76),   # shoulder
        (62, 72),   # chest
        (61, 66),   # rib
        (60, 60),   # waist start
        (59, 56),   # waist narrow
        (60, 52),   # hip start
        (62, 48),   # hip wide
        (62, 44),   # hip
        (60, 40),   # upper thigh outer
        (59, 35),   # thigh
        (58, 30),   # mid thigh
        (57, 25),   # knee area
        (56.5, 22), # below knee
        (56, 18),   # calf
        (55.5, 14), # lower calf
        (55, 10),   # ankle
        (56, 8),    # heel
        (57, 6),    # foot
        (56, 5),    # toe
    ]

    torso_left = [(100 - x, y) for x, y in torso_right][::-1]

    # Crotch / inner legs
    inner_right = [
        (56, 5),    # right foot
        (54, 8),    # inner ankle
        (53, 14),   # inner calf
        (53.5, 22), # inner knee
        (54, 30),   # inner thigh
        (53.5, 35),
        (53, 40),   # inner upper thigh
        (52, 43),   # crotch
    ]

    inner_left = [(100 - x, y) for x, y in inner_right][::-1]

    # Head outline
    head = [
        (50, 95),   # top
        (46, 93),   # left
        (45, 89),
        (45.5, 85),
        (48, 83),   # chin left
        (50, 82),   # chin center
        (52, 83),   # chin right
        (54.5, 85),
        (55, 89),
        (54, 93),
        (50, 95),
    ]

    # Draw body fill
    body_fill_right = torso_right + inner_right[::-1]
    body_fill_left = [(100 - x, y) for x, y in torso_right][::-1] + \
                     [(100 - x, y) for x, y in inner_right]

    # Draw filled body shape
    # Right leg
    right_leg = torso_right[7:] + inner_right[::-1]  # from hip down + inner back up
    ax.fill([p[0] for p in right_leg], [p[1] for p in right_leg],
            color='#1a2540', alpha=0.35, zorder=1)

    left_leg = [(100-x, y) for x, y in torso_right[7:]] + \
               [(100-x, y) for x, y in inner_right[::-1]]
    ax.fill([p[0] for p in left_leg], [p[1] for p in left_leg],
            color='#1a2540', alpha=0.35, zorder=1)

    # Torso
    torso_full = torso_right[:8] + [(100-x, y) for x, y in torso_right[:8]][::-1]
    ax.fill([p[0] for p in torso_full], [p[1] for p in torso_full],
            color='#1a2540', alpha=0.4, zorder=1)

    # Head
    ax.fill([p[0] for p in head], [p[1] for p in head],
            color='#1a2540', alpha=0.4, zorder=1)

    # Neck
    neck = [(47, 81), (53, 81), (54, 78), (46, 78)]
    ax.fill([p[0] for p in neck], [p[1] for p in neck],
            color='#1a2540', alpha=0.35, zorder=1)

    # Right arm
    right_arm_outer = right_outline[9:]  # from shoulder down
    right_arm_inner = [
        (62.5, 42),
        (60, 44),
        (60, 48),
        (61, 53),
        (61.5, 58),
        (62, 63),
        (62.5, 68),
        (63, 73),
        (62, 76),
    ]
    right_arm = right_arm_outer + right_arm_inner[::-1]
    ax.fill([p[0] for p in right_arm], [p[1] for p in right_arm],
            color='#1a2540', alpha=0.3, zorder=1)

    left_arm = [(100-x, y) for x, y in right_arm]
    ax.fill([p[0] for p in left_arm], [p[1] for p in left_arm],
            color='#1a2540', alpha=0.3, zorder=1)

    # Body outline edges (subtle glow)
    for pts_set in [head, torso_right, [(100-x,y) for x,y in torso_right],
                    inner_right, [(100-x,y) for x,y in inner_right]]:
        xs = [p[0] for p in pts_set]
        ys = [p[1] for p in pts_set]
        ax.plot(xs, ys, color='#3a5580', alpha=0.25, linewidth=0.8, zorder=2)

    # ── ORGANS (subtle outlines) ──
    # Heart
    heart = Ellipse((50, 68), 5, 6, angle=-15, facecolor='#3a1520',
                     edgecolor='#aa3040', linewidth=0.6, alpha=0.4, zorder=2)
    ax.add_patch(heart)

    # Lungs
    lung_r = Ellipse((56, 70), 8, 12, facecolor='#152035',
                      edgecolor='#2a4060', linewidth=0.4, alpha=0.25, zorder=1.5)
    lung_l = Ellipse((44, 70), 8, 12, facecolor='#152035',
                      edgecolor='#2a4060', linewidth=0.4, alpha=0.25, zorder=1.5)
    ax.add_patch(lung_r)
    ax.add_patch(lung_l)

    # Liver
    liver_pts = [(53, 62), (57, 63), (60, 61), (59, 58), (55, 57), (52, 59)]
    ax.fill([p[0] for p in liver_pts], [p[1] for p in liver_pts],
            color='#2a1a15', edgecolor='#5a3a2a', linewidth=0.4, alpha=0.35, zorder=1.8)

    # Kidneys
    kidney_r = Ellipse((57, 56), 2.5, 4, angle=10, facecolor='#1a1528',
                        edgecolor='#3a3050', linewidth=0.4, alpha=0.35, zorder=1.8)
    kidney_l = Ellipse((43, 56.5), 2.5, 4, angle=-10, facecolor='#1a1528',
                        edgecolor='#3a3050', linewidth=0.4, alpha=0.35, zorder=1.8)
    ax.add_patch(kidney_r)
    ax.add_patch(kidney_l)

    # Spleen
    spleen = Ellipse((41, 60), 2.5, 4, angle=-20, facecolor='#1a1525',
                      edgecolor='#3a2a45', linewidth=0.4, alpha=0.3, zorder=1.8)
    ax.add_patch(spleen)

    # Brain (inside head)
    brain = Ellipse((50, 90), 7, 6, facecolor='#1a1830',
                     edgecolor='#3a3560', linewidth=0.4, alpha=0.3, zorder=1.5)
    ax.add_patch(brain)


# =============================================================================
# MAIN CIRCULATORY SYSTEM
# =============================================================================

def draw_circulatory_system(ax):
    """Draw the complete circulatory system with WSS color coding."""

    # ================================================================
    # ARTERIAL SYSTEM (warm colors: yellow → orange → red)
    # ================================================================

    # ── AORTA (main trunk) ──
    # Ascending aorta
    draw_vessel(ax, [(50, 66), (50.5, 68), (51, 71), (51.5, 73), (52, 75)],
                wss=(10, 70), width=3.8, zorder=10, glow=True)

    # Aortic arch
    draw_vessel(ax, [(52, 75), (52.5, 76), (52, 77), (50, 77.5), (48, 77)],
                wss=(10, 70), width=3.5, zorder=10)

    # Descending thoracic aorta
    draw_vessel(ax, [(48, 77), (48.5, 75), (49, 72), (49.5, 68), (50, 64),
                     (50, 60), (50, 56), (50, 52), (50, 48)],
                wss=(10, 70), width=3.2, zorder=10)

    # Abdominal aorta
    draw_vessel(ax, [(50, 48), (50, 44), (50, 42)],
                wss=(10, 70), width=2.8, zorder=10)

    # ── CAROTID ARTERIES ──
    # Right common carotid
    draw_vessel(ax, [(52, 75), (52.5, 78), (52, 80), (51.5, 83),
                     (51, 86), (51, 89), (51.5, 92)],
                wss=(10, 20), width=1.5, zorder=9)

    # Left common carotid
    draw_vessel(ax, [(50, 77.5), (49, 79), (48.5, 82), (48.5, 85),
                     (49, 88), (49, 91), (49, 93)],
                wss=(10, 20), width=1.5, zorder=9)

    # ── SUBCLAVIAN → BRACHIAL → RADIAL (arms) ──
    # Right subclavian
    draw_vessel(ax, [(52, 75), (55, 76), (58, 76), (62, 75)],
                wss=(10, 70), width=1.8, zorder=8)
    # Right axillary/brachial
    draw_vessel(ax, [(62, 75), (63, 72), (63, 68), (62.5, 64),
                     (62, 60), (61.5, 56), (61, 52), (61, 48),
                     (61, 45)],
                wss=(10, 70), width=1.3, zorder=8)

    # Left subclavian
    draw_vessel(ax, [(48, 77), (45, 76.5), (42, 76), (38, 75)],
                wss=(10, 70), width=1.8, zorder=8)
    # Left brachial
    draw_vessel(ax, [(38, 75), (37, 72), (37, 68), (37.5, 64),
                     (38, 60), (38.5, 56), (39, 52), (39, 48),
                     (39, 45)],
                wss=(10, 70), width=1.3, zorder=8)

    # ── CORONARY ARTERIES ──
    draw_vessel(ax, [(50.5, 68), (52, 67.5), (53, 66.5), (52.5, 65)],
                wss=(10, 70), width=0.7, zorder=11)
    draw_vessel(ax, [(50.5, 68), (49, 67), (48, 66), (48.5, 64.5)],
                wss=(10, 70), width=0.7, zorder=11)

    # ── PULMONARY ARTERIES ──
    draw_vessel(ax, [(50, 68), (52, 69), (54, 70), (56, 71)],
                wss=(10, 30), width=1.8, zorder=7, alpha=0.85)
    draw_vessel(ax, [(50, 68), (48, 69.5), (46, 71), (44, 71.5)],
                wss=(10, 30), width=1.8, zorder=7, alpha=0.85)

    # ── CELIAC / HEPATIC / SPLENIC ──
    # Celiac trunk
    draw_vessel(ax, [(50, 61), (52, 61.5), (54, 62)],
                wss=(10, 70), width=1.2, zorder=9)
    # Hepatic artery
    draw_vessel(ax, [(54, 62), (56, 62), (57.5, 61)],
                wss=(10, 70), width=1.0, zorder=9)
    # Splenic artery
    draw_vessel(ax, [(50, 61), (48, 61), (45, 60.5), (42, 60)],
                wss=(10, 70), width=0.9, zorder=8)

    # ── RENAL ARTERIES ──
    draw_vessel(ax, [(50, 56), (52, 56.5), (54, 56.5), (56, 56)],
                wss=(10, 70), width=1.2, zorder=9)
    draw_vessel(ax, [(50, 57), (48, 57), (46, 57), (44, 56.5)],
                wss=(10, 70), width=1.2, zorder=9)

    # ── MESENTERIC ARTERIES ──
    draw_vessel(ax, [(50, 54), (52, 53), (54, 51)],
                wss=(10, 70), width=0.8, zorder=8)
    draw_vessel(ax, [(50, 50), (48, 49), (46, 48)],
                wss=(10, 70), width=0.8, zorder=8)

    # ── ILIAC ARTERIES → FEMORAL ──
    # Right common iliac
    draw_vessel(ax, [(50, 42), (51, 41), (52, 40), (53, 39)],
                wss=(10, 70), width=2.2, zorder=10)
    # Right external iliac → femoral
    draw_vessel(ax, [(53, 39), (54, 37), (55, 34), (55.5, 30),
                     (56, 26), (56, 22), (55.5, 18), (55, 14),
                     (55, 10), (55, 7)],
                wss=(10, 70), width=1.6, zorder=9)

    # Left common iliac
    draw_vessel(ax, [(50, 42), (49, 41), (48, 40), (47, 39)],
                wss=(10, 70), width=2.2, zorder=10)
    # Left femoral
    draw_vessel(ax, [(47, 39), (46, 37), (45, 34), (44.5, 30),
                     (44, 26), (44, 22), (44.5, 18), (45, 14),
                     (45, 10), (45, 7)],
                wss=(10, 70), width=1.6, zorder=9)

    # ── ARTERIOLES (thin, high WSS ~55) ──
    # Renal arterioles
    draw_vessel(ax, [(56, 56), (57.5, 55.5), (58.5, 55)],
                wss=(40, 60), width=0.5, zorder=8, glow=True)
    draw_vessel(ax, [(44, 56.5), (42.5, 56), (41.5, 55.5)],
                wss=(40, 60), width=0.5, zorder=8, glow=True)
    # Hepatic arterioles → sinusoidal transition
    draw_vessel_varying_wss(ax,
        [(57.5, 61), (58.5, 60.5), (59, 59.5), (59, 58.5)],
        wss_values=[50, 20, 5, 0.5],
        width=0.5, zorder=9)

    # ================================================================
    # VENOUS SYSTEM (cool colors: blue → cyan)
    # ================================================================

    # ── INFERIOR VENA CAVA ──
    draw_vessel(ax, [(51.5, 66), (51.5, 64), (51.5, 60), (51.5, 56),
                     (51, 52), (51, 48), (51, 44), (51, 42)],
                wss=(1, 6), width=3.5, zorder=6, depth_fade=0.2)

    # ── SUPERIOR VENA CAVA ──
    draw_vessel(ax, [(51.5, 66), (52, 68), (53, 72), (53.5, 75)],
                wss=(1, 6), width=3.0, zorder=6, depth_fade=0.15)

    # ── JUGULAR VEINS ──
    draw_vessel(ax, [(53.5, 75), (53.5, 78), (53, 82), (52.5, 86),
                     (52, 89), (52, 91)],
                wss=(1, 6), width=1.4, zorder=5, depth_fade=0.15)
    draw_vessel(ax, [(53.5, 75), (51, 77), (49.5, 80), (49, 84),
                     (48, 87), (47.5, 91)],
                wss=(1, 6), width=1.4, zorder=5, depth_fade=0.15)

    # ── SUBCLAVIAN VEINS → ARM VEINS ──
    draw_vessel(ax, [(53.5, 75), (56, 75), (60, 74), (63, 73)],
                wss=(1, 6), width=1.5, zorder=5, depth_fade=0.2)
    draw_vessel(ax, [(63, 73), (63.5, 69), (63, 65), (62.5, 61),
                     (62, 57), (61.5, 53), (61.5, 49), (61.5, 46)],
                wss=(1, 6), width=1.1, zorder=5, depth_fade=0.2)

    draw_vessel(ax, [(53.5, 75), (51, 76), (46, 75.5), (41, 74.5), (37.5, 73)],
                wss=(1, 6), width=1.5, zorder=5, depth_fade=0.2)
    draw_vessel(ax, [(37.5, 73), (37, 69), (37, 65), (37.5, 61),
                     (38, 57), (38.5, 53), (38.5, 49), (38.5, 46)],
                wss=(1, 6), width=1.1, zorder=5, depth_fade=0.2)

    # ── HEPATIC VEINS ──
    draw_vessel(ax, [(57, 61), (55, 62.5), (53, 63.5), (51.5, 64)],
                wss=(1, 6), width=1.0, zorder=6, depth_fade=0.1)

    # ── PORTAL VEIN ──
    draw_vessel(ax, [(51, 50), (52, 52), (53, 55), (55, 58), (56, 60)],
                wss=(1, 6), width=1.3, zorder=5, depth_fade=0.2)

    # ── RENAL VEINS ──
    draw_vessel(ax, [(56.5, 55.5), (54, 55.5), (52, 55.5), (51.5, 56)],
                wss=(1, 6), width=1.0, zorder=5, depth_fade=0.15)
    draw_vessel(ax, [(43.5, 56), (46, 56.5), (48, 57), (51, 57)],
                wss=(1, 6), width=1.0, zorder=5, depth_fade=0.15)

    # ── ILIAC VEINS → FEMORAL VEINS ──
    draw_vessel(ax, [(51, 42), (52, 41), (53, 40), (54, 39)],
                wss=(1, 6), width=2.0, zorder=5, depth_fade=0.2)
    draw_vessel(ax, [(54, 39), (55, 36), (56, 32), (56.5, 28),
                     (57, 24), (57, 20), (56.5, 16), (56, 12),
                     (56, 8)],
                wss=(1, 6), width=1.3, zorder=5, depth_fade=0.2)

    draw_vessel(ax, [(51, 42), (50, 41), (49, 40), (48, 39)],
                wss=(1, 6), width=2.0, zorder=5, depth_fade=0.2)
    draw_vessel(ax, [(48, 39), (47, 36), (46, 32), (45.5, 28),
                     (45, 24), (45, 20), (45.5, 16), (46, 12),
                     (46, 8)],
                wss=(1, 6), width=1.3, zorder=5, depth_fade=0.2)

    # ── PULMONARY VEINS ──
    draw_vessel(ax, [(56, 69), (54, 68), (52, 67.5), (51, 67)],
                wss=(1, 6), width=1.2, zorder=6, depth_fade=0.1)
    draw_vessel(ax, [(44, 70), (46, 69), (48, 68), (49, 67.5)],
                wss=(1, 6), width=1.2, zorder=6, depth_fade=0.1)

    # ================================================================
    # LYMPHATIC SYSTEM (deep blue/indigo)
    # ================================================================

    # Thoracic duct
    draw_vessel(ax, [(49, 42), (48.5, 46), (48, 52), (47.5, 58),
                     (47.5, 64), (47, 70), (47, 74), (47.5, 76)],
                wss=(0.1, 0.6), width=0.6, zorder=4, alpha=0.7)

    # Right lymphatic duct
    draw_vessel(ax, [(53, 74), (54.5, 75.5), (55, 76)],
                wss=(0.1, 0.6), width=0.4, zorder=4, alpha=0.6)

    # ================================================================
    # MICROVASCULAR BEDS (scatter effects)
    # ================================================================

    # Hepatic sinusoidal bed — ultra-low WSS
    np.random.seed(42)
    n_sin = 300
    sin_x = 55 + np.random.normal(0, 2.0, n_sin)
    sin_y = 60 + np.random.normal(0, 1.8, n_sin)
    sin_wss = np.random.uniform(0.1, 0.6, n_sin)
    sin_colors = WSS_CMAP(WSS_NORM(sin_wss))
    sin_colors[:, 3] = np.random.uniform(0.15, 0.5, n_sin)
    sizes = np.random.uniform(1, 8, n_sin)
    ax.scatter(sin_x, sin_y, s=sizes, c=sin_colors, zorder=3, edgecolors='none')

    # Kidney microvascular beds
    for kx, ky in [(57, 56), (43, 56.5)]:
        n_k = 80
        k_x = kx + np.random.normal(0, 1.0, n_k)
        k_y = ky + np.random.normal(0, 1.5, n_k)
        k_wss = np.random.uniform(0.5, 8, n_k)
        k_colors = WSS_CMAP(WSS_NORM(k_wss))
        k_colors[:, 3] = 0.3
        ax.scatter(k_x, k_y, s=np.random.uniform(1, 5, n_k),
                   c=k_colors, zorder=2, edgecolors='none')

    # Pulmonary capillary beds
    for lx, ly in [(56, 70), (44, 70)]:
        n_l = 120
        l_x = lx + np.random.normal(0, 2.5, n_l)
        l_y = ly + np.random.normal(0, 3.5, n_l)
        l_wss = np.random.uniform(1, 10, n_l)
        l_colors = WSS_CMAP(WSS_NORM(l_wss))
        l_colors[:, 3] = 0.15
        ax.scatter(l_x, l_y, s=np.random.uniform(1, 4, n_l),
                   c=l_colors, zorder=1.5, edgecolors='none')


# =============================================================================
# PATHOLOGICAL MARKERS
# =============================================================================

def draw_pathological_markers(ax):
    """Draw annotated pathological hotspots."""

    # ── ATHEROSCLEROTIC PLAQUE SITE (carotid bifurcation) ──
    ax.plot(51.5, 84, 'D', color='#ffdd33', markersize=7, zorder=20,
            markeredgecolor='white', markeredgewidth=0.5)
    # Glow ring
    glow = Circle((51.5, 84), 1.8, facecolor='none', edgecolor='#ffdd33',
                   linewidth=0.8, alpha=0.4, linestyle='--', zorder=19)
    ax.add_patch(glow)

    # Annotation
    ax.annotate(
        'Atherosclerotic\nPlaque Site\nWSS < 4 dyne/cm\u00b2',
        xy=(51.5, 84), xytext=(66, 86),
        fontsize=6.5, color='#ffdd88', fontweight='bold',
        ha='left', va='center',
        arrowprops=dict(arrowstyle='->', color='#ffdd88', lw=0.8,
                        connectionstyle='arc3,rad=0.15'),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1a30',
                  edgecolor='#ffdd44', alpha=0.85, linewidth=0.5),
        zorder=25,
    )

    # ── STENOTIC HOTSPOT ──
    ax.plot(52, 80, '*', color='#ff2233', markersize=10, zorder=20,
            markeredgecolor='white', markeredgewidth=0.3)
    glow2 = Circle((52, 80), 1.5, facecolor='#ff0000', edgecolor='none',
                    alpha=0.1, zorder=18)
    ax.add_patch(glow2)

    ax.annotate(
        'Stenotic Hotspot\nWSS > 1000 dyne/cm\u00b2',
        xy=(52, 80), xytext=(66, 80),
        fontsize=6.5, color='#ff8888', fontweight='bold',
        ha='left', va='center',
        arrowprops=dict(arrowstyle='->', color='#ff8888', lw=0.8,
                        connectionstyle='arc3,rad=-0.1'),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1020',
                  edgecolor='#ff4444', alpha=0.85, linewidth=0.5),
        zorder=25,
    )

    # ── TUMOR VASCULATURE ──
    np.random.seed(99)
    n_tumor = 60
    tx = 44 + np.random.normal(0, 1.2, n_tumor)
    ty = 71 + np.random.normal(0, 1.5, n_tumor)
    t_wss = np.random.uniform(0.3, 4, n_tumor)
    t_colors = WSS_CMAP(WSS_NORM(t_wss))
    t_colors[:, 3] = 0.5
    ax.scatter(tx, ty, s=np.random.uniform(2, 10, n_tumor),
               c=t_colors, zorder=15, edgecolors='none', marker='s')

    # Tumor outline
    tumor_circle = Circle((44, 71), 2.5, facecolor='none',
                           edgecolor='#ff4466', linewidth=0.6,
                           linestyle=':', alpha=0.5, zorder=14)
    ax.add_patch(tumor_circle)

    ax.annotate(
        'Tumor Vasculature\nLow & oscillatory WSS\nImpaired NP penetration',
        xy=(44, 71), xytext=(28, 73),
        fontsize=6.5, color='#ff8899', fontweight='bold',
        ha='right', va='center',
        arrowprops=dict(arrowstyle='->', color='#ff8899', lw=0.8,
                        connectionstyle='arc3,rad=0.15'),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1020',
                  edgecolor='#ff4466', alpha=0.85, linewidth=0.5),
        zorder=25,
    )

    # ── HEPATIC SINUSOIDAL ANNOTATION ──
    ax.annotate(
        'Hepatic Sinusoidal Bed\nWSS 0.1\u20130.6 dyne/cm\u00b2\nUltra-low shear: NP margination zone',
        xy=(56, 60), xytext=(66, 58),
        fontsize=6.5, color='#6688cc', fontweight='bold',
        ha='left', va='center',
        arrowprops=dict(arrowstyle='->', color='#6688cc', lw=0.8,
                        connectionstyle='arc3,rad=-0.1'),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#0a1028',
                  edgecolor='#4466aa', alpha=0.85, linewidth=0.5),
        zorder=25,
    )


# =============================================================================
# ORGAN LABELS
# =============================================================================

def draw_organ_labels(ax):
    """Add subtle organ labels."""
    labels = [
        (50, 90, 'Brain', '#4a5580'),
        (50, 68, '\u2764', '#cc3040'),     # heart symbol
        (56, 70.5, 'R. Lung', '#2a4565'),
        (44, 70.5, 'L. Lung', '#2a4565'),
        (56, 62, 'Liver', '#5a4030'),
        (57.5, 56, 'R. Kidney', '#3a3050'),
        (42.5, 56.5, 'L. Kidney', '#3a3050'),
        (41, 60.5, 'Spleen', '#3a2a45'),
    ]

    for x, y, txt, color in labels:
        ax.text(x, y, txt, fontsize=5.5, color=color, ha='center', va='center',
                fontstyle='italic', alpha=0.65, zorder=3,
                fontweight='normal')


# =============================================================================
# WSS DATA TABLE (inset)
# =============================================================================

def draw_wss_table(ax_table):
    """Draw the WSS reference data table as an inset."""
    ax_table.set_facecolor('#0d1220')
    ax_table.set_xlim(0, 10)
    ax_table.set_ylim(0, 10)
    ax_table.axis('off')

    # Title
    ax_table.text(5, 9.5, 'Wall Shear Stress Reference', fontsize=8,
                   color='white', ha='center', va='top', fontweight='bold',
                   fontstyle='italic')

    data = [
        ('Hepatic Sinusoids',     0.1,  0.6,  'Fenestrated endothelium'),
        ('Lymphatic Vessels',     0.1,  0.6,  'Near-stagnant drainage'),
        ('Venous Circulation',    1,    6,    'Low-pressure return'),
        ('Atherosclerotic Sites', 0.5,  4,    'Plaque-prone (pathological)'),
        ('Carotid Arteries',      10,   20,   'Endothelial homeostasis'),
        ('Arterioles',            40,   60,   'NP margination driver'),
        ('General Arterial',      10,   70,   'Pulsatile systemic flow'),
        ('Stenotic Regions',      100,  1200, 'Bilayer rupture risk'),
    ]

    y_pos = 8.8
    for region, wss_lo, wss_hi, note in data:
        y_pos -= 0.95

        # Color swatch
        wss_mean = np.sqrt(wss_lo * wss_hi)
        color = WSS_CMAP(WSS_NORM(wss_mean))
        rect = FancyBboxPatch((0.2, y_pos - 0.25), 0.5, 0.5,
                               boxstyle='round,pad=0.05',
                               facecolor=color, edgecolor='none', alpha=0.9)
        ax_table.add_patch(rect)

        # Region name
        ax_table.text(1.0, y_pos, region, fontsize=6, color='#ccddee',
                       ha='left', va='center', fontweight='bold')

        # WSS range
        if wss_hi >= 1000:
            wss_str = f'>{wss_lo}\u2013{wss_hi}'
        else:
            wss_str = f'{wss_lo}\u2013{wss_hi}'
        ax_table.text(6.2, y_pos, wss_str, fontsize=5.5, color='#aabbcc',
                       ha='center', va='center', family='monospace')

        # Unit
        ax_table.text(8.0, y_pos, note, fontsize=4.5, color='#778899',
                       ha='left', va='center', fontstyle='italic')

    # Unit label
    ax_table.text(6.2, y_pos - 1.0, 'dyne/cm\u00b2', fontsize=5, color='#667788',
                   ha='center', va='center', fontstyle='italic')


# =============================================================================
# MAIN FIGURE ASSEMBLY
# =============================================================================

def build_figure():
    """Assemble the complete figure."""

    fig = plt.figure(figsize=(FIG_WIDTH, FIG_HEIGHT), facecolor=BG_COLOR)

    # Main axes for the body
    gs = gridspec.GridSpec(2, 2, width_ratios=[3, 1], height_ratios=[5, 1],
                           hspace=0.02, wspace=0.02,
                           left=0.02, right=0.98, top=0.96, bottom=0.02)

    ax_main = fig.add_subplot(gs[0, 0])
    ax_main.set_facecolor(BG_COLOR)
    ax_main.set_xlim(30, 72)
    ax_main.set_ylim(0, 100)
    ax_main.set_aspect('equal')
    ax_main.axis('off')

    # Colorbar axes
    ax_cbar = fig.add_subplot(gs[0, 1])
    ax_cbar.set_facecolor(BG_COLOR)
    ax_cbar.axis('off')

    # WSS table axes
    ax_table = fig.add_subplot(gs[1, :])

    # ── BACKGROUND GRADIENT ──
    gradient = np.linspace(0, 1, 256).reshape(1, -1).T
    bg_cmap = LinearSegmentedColormap.from_list('bg',
        ['#060a14', '#0a1020', '#0f1628', '#0a1020', '#060a14'])
    ax_main.imshow(gradient, aspect='auto', cmap=bg_cmap, alpha=0.3,
                    extent=[30, 72, 0, 100], zorder=0)

    # Subtle radial vignette effect
    for r, a in [(40, 0.02), (30, 0.03), (20, 0.04)]:
        vignette = Circle((50, 55), r, facecolor='none', edgecolor=BG_COLOR,
                           linewidth=r * 0.5, alpha=a, zorder=0)
        ax_main.add_patch(vignette)

    # ── DRAW LAYERS ──
    print('  Drawing body silhouette...')
    draw_body_silhouette(ax_main)

    print('  Drawing circulatory system...')
    draw_circulatory_system(ax_main)

    print('  Drawing pathological markers...')
    draw_pathological_markers(ax_main)

    print('  Drawing organ labels...')
    draw_organ_labels(ax_main)

    # ── TITLE ──
    fig.text(0.38, 0.975,
             'Wall Shear Stress Distribution\nin the Human Circulatory System',
             fontsize=16, color='white', ha='center', va='top',
             fontweight='bold', fontfamily='sans-serif',
             linespacing=1.3)

    fig.text(0.38, 0.94,
             'Color intensity indicates WSS magnitude (log scale, 0.1\u20131000+ dyne/cm\u00b2)',
             fontsize=8, color='#8899aa', ha='center', va='top',
             fontstyle='italic')

    # ── COLORBAR ──
    print('  Drawing colorbar...')
    # Create colorbar manually in the right panel
    cbar_left = 0.82
    cbar_bottom = 0.25
    cbar_width = 0.025
    cbar_height = 0.50

    ax_cb = fig.add_axes([cbar_left, cbar_bottom, cbar_width, cbar_height])
    ax_cb.set_facecolor('none')

    cb = ColorbarBase(ax_cb, cmap=WSS_CMAP, norm=WSS_NORM,
                       orientation='vertical')
    cb.set_label('Wall Shear Stress (dyne/cm\u00b2)', fontsize=9, color='white',
                  labelpad=10)
    cb.set_ticks([0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000])
    cb.set_ticklabels(['0.1', '0.5', '1', '5', '10', '50', '100', '500', '1000'])
    cb.ax.tick_params(colors='white', labelsize=7)
    cb.outline.set_edgecolor('#334455')
    cb.outline.set_linewidth(0.5)

    # Colorbar annotations
    annotations_cb = [
        (0.3, 'Sinusoids\nLymphatics', '#4466aa', 'right'),
        (3, 'Veins', '#00aacc', 'right'),
        (15, 'Carotid\nArteries', '#88cc00', 'right'),
        (55, 'Arterioles', '#ffaa00', 'right'),
        (500, 'Stenosis', '#dd0044', 'right'),
    ]

    for wss_val, label, color, ha in annotations_cb:
        y_norm = WSS_NORM(wss_val)
        fig.text(cbar_left + cbar_width + 0.035, cbar_bottom + y_norm * cbar_height,
                 label, fontsize=5.5, color=color, ha='left', va='center',
                 fontweight='bold', fontstyle='italic')
        # Small tick line
        tick_y = cbar_bottom + y_norm * cbar_height
        tick_line = Line2D(
            [cbar_left + cbar_width + 0.005, cbar_left + cbar_width + 0.025],
            [tick_y, tick_y],
            color=color, linewidth=0.5, alpha=0.6,
            transform=fig.transFigure, clip_on=False)
        fig.add_artist(tick_line)

    # ── WSS DATA TABLE ──
    print('  Drawing WSS reference table...')
    draw_wss_table(ax_table)

    # ── LEGEND (vessel types) ──
    legend_elements = [
        Line2D([0], [0], color=WSS_CMAP(WSS_NORM(30)), linewidth=3,
               label='Arterial (10\u201370 dyne/cm\u00b2)'),
        Line2D([0], [0], color=WSS_CMAP(WSS_NORM(3)), linewidth=3,
               label='Venous (1\u20136 dyne/cm\u00b2)'),
        Line2D([0], [0], color=WSS_CMAP(WSS_NORM(0.3)), linewidth=1.5,
               label='Lymphatic (0.1\u20130.6 dyne/cm\u00b2)'),
        Line2D([0], [0], color=WSS_CMAP(WSS_NORM(55)), linewidth=1,
               label='Arterioles (~55 dyne/cm\u00b2)'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor='#ffdd33',
               markersize=6, linewidth=0, label='Atherosclerotic site'),
        Line2D([0], [0], marker='*', color='w', markerfacecolor='#ff2233',
               markersize=8, linewidth=0, label='Stenotic hotspot'),
    ]

    leg = ax_main.legend(handles=legend_elements, loc='lower left',
                          fontsize=6.5, facecolor='#0d1220',
                          edgecolor='#334455', labelcolor='#ccddee',
                          framealpha=0.9, borderpad=0.8,
                          handlelength=2.5, handletextpad=0.6,
                          title='Vessel Type', title_fontsize=7)
    leg.get_title().set_color('#8899aa')
    leg.get_title().set_fontweight('bold')

    # ── CITATION ──
    fig.text(0.5, 0.005,
             'Data: Modh et al., "Resolving the Biomechanical Blind Spot in Nanomedicine Translation" \u2014 ACS Nano (2025)',
             fontsize=6, color='#556677', ha='center', va='bottom',
             fontstyle='italic')

    return fig


# =============================================================================
# MAIN
# =============================================================================

def main():
    print('Generating professional WSS circulatory system figure...')

    fig = build_figure()

    output_path = 'wss_circulatory_system.png'
    print(f'  Saving to {output_path} at {DPI} DPI...')
    fig.savefig(output_path, dpi=DPI, facecolor=BG_COLOR,
                bbox_inches='tight', pad_inches=0.1)

    # Also save PDF for vector quality
    pdf_path = 'wss_circulatory_system.pdf'
    print(f'  Saving PDF to {pdf_path}...')
    fig.savefig(pdf_path, facecolor=BG_COLOR,
                bbox_inches='tight', pad_inches=0.1)

    plt.close(fig)

    import os
    png_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f'\nDone! Output:')
    print(f'  PNG: {output_path} ({png_size:.1f} MB, {DPI} DPI)')
    print(f'  PDF: {pdf_path} (vector)')


if __name__ == '__main__':
    main()
