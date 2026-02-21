#!/usr/bin/env python3
"""
3D Interactive Visualization of Wall Shear Stress in the Human Circulatory System
==================================================================================

Generates an interactive 3D HTML visualization showing the human circulatory system
with color-coded wall shear stress (WSS) values. The visualization is fully
programmatic — no external mesh files required.

Data source: "Resolving the Biomechanical Blind Spot in Nanomedicine Translation"
             Modh et al., 2025

Usage:
    python generate_viz.py

Output:
    docs/index.html — standalone interactive visualization for GitHub Pages
"""

import numpy as np
from scipy.interpolate import CubicSpline
import plotly.graph_objects as go
import os

# =============================================================================
# SECTION 1: Constants and Color Mapping
# =============================================================================

# WSS spans 4 orders of magnitude → log scale essential
WSS_LOG_MIN = -1.0   # log10(0.1)
WSS_LOG_MAX = 3.0    # log10(1000)

# Custom colorscale: blue (low WSS) → cyan → green → yellow → orange → red → magenta (extreme)
WSS_COLORSCALE = [
    [0.00, 'rgb(10, 20, 120)'],       # 0.1 dyne/cm² — deep blue (sinusoids)
    [0.15, 'rgb(0, 100, 220)'],       # ~0.5 — blue
    [0.25, 'rgb(0, 180, 220)'],       # 1 — cyan (veins)
    [0.375, 'rgb(0, 200, 80)'],       # ~3 — green
    [0.50, 'rgb(220, 220, 0)'],       # 10 — yellow (normal arteries)
    [0.625, 'rgb(255, 150, 0)'],      # ~30 — orange
    [0.75, 'rgb(230, 30, 0)'],        # 100 — red (stenotic)
    [0.875, 'rgb(200, 0, 100)'],      # ~300 — magenta
    [1.00, 'rgb(160, 0, 200)'],       # 1000 — purple (severe stenosis)
]

COLORBAR_TICKVALS = [np.log10(v) for v in [0.1, 1, 10, 100, 1000]]
COLORBAR_TICKTEXT = ['0.1', '1', '10', '100', '1000']


# =============================================================================
# SECTION 2: Tube Mesh Generation (Rotation-Minimizing Frames)
# =============================================================================

def generate_tube_mesh(path_points, radius, n_along=50, n_radial=12):
    """
    Generate a triangulated cylindrical mesh around a 3D path curve.

    Uses Rotation-Minimizing Frames (RMF) via double-reflection to prevent
    twist artifacts that naive Frenet frames produce.

    Args:
        path_points: List of (x, y, z) tuples defining vessel centerline
        radius: Tube radius in cm (scalar or array for varying radius)
        n_along: Number of samples along the path
        n_radial: Number of vertices per cross-section ring

    Returns:
        (x, y, z, i, j, k): Vertex coordinates and triangle face indices
    """
    pts = np.array(path_points, dtype=float)
    n_pts = len(pts)

    if n_pts < 2:
        return None

    # Interpolate path with cubic spline for smoothness
    if n_pts >= 4:
        t_orig = np.linspace(0, 1, n_pts)
        t_new = np.linspace(0, 1, n_along)
        cs_x = CubicSpline(t_orig, pts[:, 0])
        cs_y = CubicSpline(t_orig, pts[:, 1])
        cs_z = CubicSpline(t_orig, pts[:, 2])
        path = np.column_stack([cs_x(t_new), cs_y(t_new), cs_z(t_new)])
    elif n_pts >= 2:
        t_orig = np.linspace(0, 1, n_pts)
        t_new = np.linspace(0, 1, n_along)
        path = np.column_stack([
            np.interp(t_new, t_orig, pts[:, 0]),
            np.interp(t_new, t_orig, pts[:, 1]),
            np.interp(t_new, t_orig, pts[:, 2]),
        ])
    else:
        return None

    # Compute tangent vectors
    tangents = np.zeros_like(path)
    tangents[0] = path[1] - path[0]
    tangents[-1] = path[-1] - path[-2]
    tangents[1:-1] = path[2:] - path[:-2]
    norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    norms[norms < 1e-12] = 1e-12
    tangents = tangents / norms

    # Initial normal: find vector not parallel to first tangent
    t0 = tangents[0]
    seed = np.array([0, 0, 1]) if abs(np.dot(t0, [0, 0, 1])) < 0.9 else np.array([1, 0, 0])
    normal = np.cross(t0, seed)
    normal = normal / (np.linalg.norm(normal) + 1e-12)

    # Propagate frame using double-reflection RMF method
    normals = np.zeros_like(path)
    normals[0] = normal
    for idx in range(1, n_along):
        v1 = path[idx] - path[idx - 1]
        c1 = np.dot(v1, v1)
        if c1 < 1e-12:
            normals[idx] = normals[idx - 1]
            continue
        rL = normals[idx - 1] - (2.0 / c1) * np.dot(v1, normals[idx - 1]) * v1
        tL = tangents[idx - 1] - (2.0 / c1) * np.dot(v1, tangents[idx - 1]) * v1
        v2 = tangents[idx] - tL
        c2 = np.dot(v2, v2)
        if c2 < 1e-12:
            normals[idx] = rL
        else:
            normals[idx] = rL - (2.0 / c2) * np.dot(v2, rL) * v2
        nn = np.linalg.norm(normals[idx])
        if nn > 1e-12:
            normals[idx] /= nn

    # Generate tube vertices
    angles = np.linspace(0, 2 * np.pi, n_radial, endpoint=False)
    all_x, all_y, all_z = [], [], []

    r_array = np.full(n_along, radius) if np.isscalar(radius) else np.interp(
        np.linspace(0, 1, n_along), np.linspace(0, 1, len(radius)), radius
    )

    for idx in range(n_along):
        t = tangents[idx]
        n = normals[idx]
        b = np.cross(t, n)
        b_norm = np.linalg.norm(b)
        if b_norm > 1e-12:
            b /= b_norm
        r = r_array[idx]
        for angle in angles:
            offset = r * (np.cos(angle) * n + np.sin(angle) * b)
            pt = path[idx] + offset
            all_x.append(pt[0])
            all_y.append(pt[1])
            all_z.append(pt[2])

    # Generate triangle faces connecting adjacent rings
    faces_i, faces_j, faces_k = [], [], []
    for idx in range(n_along - 1):
        for jdx in range(n_radial):
            j_next = (jdx + 1) % n_radial
            v0 = idx * n_radial + jdx
            v1 = idx * n_radial + j_next
            v2 = (idx + 1) * n_radial + jdx
            v3 = (idx + 1) * n_radial + j_next
            # Triangle 1
            faces_i.append(v0); faces_j.append(v1); faces_k.append(v2)
            # Triangle 2
            faces_i.append(v1); faces_j.append(v3); faces_k.append(v2)

    return (
        np.array(all_x), np.array(all_y), np.array(all_z),
        np.array(faces_i), np.array(faces_j), np.array(faces_k),
    )


# =============================================================================
# SECTION 3: Body Outline Generation
# =============================================================================

def generate_ellipsoid(center, radii, n_phi=14, n_theta=14):
    """Generate vertices for an ellipsoid surface."""
    cx, cy, cz = center
    rx, ry, rz = radii
    phi = np.linspace(0, np.pi, n_phi)
    theta = np.linspace(0, 2 * np.pi, n_theta)
    phi, theta = np.meshgrid(phi, theta)
    x = cx + rx * np.sin(phi) * np.cos(theta)
    y = cy + ry * np.sin(phi) * np.sin(theta)
    z = cz + rz * np.cos(phi)
    return x.flatten(), y.flatten(), z.flatten()


def create_body_outline():
    """Create semi-transparent body silhouette from parametric ellipsoids."""
    body_parts = [
        # (center, radii, label)
        ((0, -2, 12),   (17, 11, 28),  'Torso'),
        ((0, 0, 73),    (9, 9, 11),    'Head'),
        ((0, -1, 58),   (5.5, 5, 7),   'Neck'),
        # Arms
        ((20, -1, 38),  (4.5, 4, 14),  'R. Upper Arm'),
        ((24, 0, 12),   (3.5, 3, 13),  'R. Forearm'),
        ((-20, -1, 38), (4.5, 4, 14),  'L. Upper Arm'),
        ((-24, 0, 12),  (3.5, 3, 13),  'L. Forearm'),
        # Legs
        ((8, -1, -30),  (7, 6.5, 22),  'R. Thigh'),
        ((8, 0, -65),   (5, 4.5, 18),  'R. Calf'),
        ((-8, -1, -30), (7, 6.5, 22),  'L. Thigh'),
        ((-8, 0, -65),  (5, 4.5, 18),  'L. Calf'),
        # Pelvis
        ((0, -2, -10),  (14, 10, 8),   'Pelvis'),
        # Shoulders
        ((16, -1, 48),  (6, 5, 5),     'R. Shoulder'),
        ((-16, -1, 48), (6, 5, 5),     'L. Shoulder'),
    ]

    traces = []
    for center, radii, label in body_parts:
        x, y, z = generate_ellipsoid(center, radii)
        traces.append(go.Mesh3d(
            x=x, y=y, z=z,
            alphahull=0,
            opacity=0.06,
            color='rgb(160, 185, 210)',
            hoverinfo='skip',
            showscale=False,
            name='Body',
            legendgroup='body',
            showlegend=(label == 'Torso'),
            flatshading=True,
            lighting=dict(ambient=0.8, diffuse=0.2),
        ))
    return traces


# =============================================================================
# SECTION 4: Vessel Data Definitions
# =============================================================================

def define_vessels():
    """
    Define all vessels with anatomically approximate 3D paths.

    Each vessel is a dict with:
        name: Vessel name
        path: List of (x, y, z) control points in cm
        radius: Tube radius in cm
        wss_range: (min, max) WSS in dyne/cm²
        group: Legend group
        significance: Physiological description for hover
    """
    vessels = []

    # ── HEART ──
    # (Heart is rendered separately as a special shape)

    # ── ARTERIAL SYSTEM ──

    # Ascending Aorta
    vessels.append(dict(
        name='Ascending Aorta',
        path=[(1, -5, 35), (1.5, -3, 38), (2, -1, 42), (2, 1, 46)],
        radius=1.4,
        wss_range=(10, 70),
        group='Arterial',
        significance='Main conduit from heart; high pulsatile flow',
    ))

    # Aortic Arch
    vessels.append(dict(
        name='Aortic Arch',
        path=[(2, 1, 46), (1, 2, 48), (-1, 1, 49), (-2, -2, 47), (-2, -4, 45)],
        radius=1.3,
        wss_range=(10, 70),
        group='Arterial',
        significance='Curved region; disturbed flow at branch points',
    ))

    # Descending Thoracic Aorta
    vessels.append(dict(
        name='Descending Aorta',
        path=[(-2, -4, 45), (-1.5, -5, 40), (-1, -6, 32), (-0.5, -6, 22),
              (0, -6, 12), (0, -5.5, 2), (0, -5, -8)],
        radius=1.1,
        wss_range=(10, 70),
        group='Arterial',
        significance='Thoraco-abdominal conduit; sustained arterial shear',
    ))

    # Right Common Carotid
    vessels.append(dict(
        name='R. Common Carotid',
        path=[(2, 1, 46), (3, 0, 50), (3.5, -1, 55), (3.5, -1, 60),
              (3, 0, 65), (2.5, 0, 70)],
        radius=0.4,
        wss_range=(10, 20),
        group='Arterial',
        significance='WSS 10-20 dyne/cm\u00b2; bifurcation is atherosclerosis-prone site',
    ))

    # Left Common Carotid
    vessels.append(dict(
        name='L. Common Carotid',
        path=[(0, 1, 48), (-2, 0, 52), (-3, -0.5, 56), (-3.5, -0.5, 61),
              (-3, 0, 66), (-2.5, 0, 70)],
        radius=0.4,
        wss_range=(10, 20),
        group='Arterial',
        significance='WSS 10-20 dyne/cm\u00b2; promotes anti-inflammatory endothelial phenotype',
    ))

    # Right Subclavian → Brachial
    vessels.append(dict(
        name='R. Subclavian Artery',
        path=[(2, 1, 46), (6, 0, 47), (10, -1, 46), (15, -1, 44)],
        radius=0.45,
        wss_range=(10, 70),
        group='Arterial',
        significance='Supplies right upper limb',
    ))
    vessels.append(dict(
        name='R. Brachial Artery',
        path=[(15, -1, 44), (18, -1, 40), (20, -1, 34), (21, 0, 26),
              (22, 0, 18), (23, 0, 10)],
        radius=0.3,
        wss_range=(10, 70),
        group='Arterial',
        significance='Upper limb arterial supply; arteriolar WSS ~55 dyne/cm\u00b2',
    ))

    # Left Subclavian → Brachial
    vessels.append(dict(
        name='L. Subclavian Artery',
        path=[(-1, 1, 48), (-6, 0, 47), (-10, -1, 46), (-15, -1, 44)],
        radius=0.45,
        wss_range=(10, 70),
        group='Arterial',
        significance='Supplies left upper limb',
    ))
    vessels.append(dict(
        name='L. Brachial Artery',
        path=[(-15, -1, 44), (-18, -1, 40), (-20, -1, 34), (-21, 0, 26),
              (-22, 0, 18), (-23, 0, 10)],
        radius=0.3,
        wss_range=(10, 70),
        group='Arterial',
        significance='Upper limb arterial supply',
    ))

    # Celiac Trunk → Hepatic Artery
    vessels.append(dict(
        name='Hepatic Artery',
        path=[(0, -5.5, 20), (2, -3, 20), (5, -1, 21), (8, 0, 22)],
        radius=0.3,
        wss_range=(10, 70),
        group='Arterial',
        significance='Supplies liver; branches into hepatic sinusoids (WSS 0.1-0.6)',
    ))

    # Splenic Artery
    vessels.append(dict(
        name='Splenic Artery',
        path=[(0, -5.5, 20), (-2, -3, 19), (-5, -2, 18), (-9, -1, 17)],
        radius=0.25,
        wss_range=(10, 70),
        group='Arterial',
        significance='Supplies spleen; tortuosity creates oscillatory shear',
    ))

    # Renal Arteries
    vessels.append(dict(
        name='R. Renal Artery',
        path=[(0, -5.5, 14), (3, -4, 14), (6, -3, 14.5), (9, -2, 15)],
        radius=0.35,
        wss_range=(10, 70),
        group='Arterial',
        significance='Supplies right kidney; high flow/high shear organ',
    ))
    vessels.append(dict(
        name='L. Renal Artery',
        path=[(0, -5.5, 15), (-3, -4, 15), (-6, -3, 15.5), (-9, -2, 16)],
        radius=0.35,
        wss_range=(10, 70),
        group='Arterial',
        significance='Supplies left kidney',
    ))

    # Coronary Arteries
    vessels.append(dict(
        name='L. Coronary Artery',
        path=[(1, -5, 37), (3, -3, 36), (4, -4, 34), (3, -6, 33)],
        radius=0.18,
        wss_range=(10, 70),
        group='Arterial',
        significance='Supplies heart muscle; critical for cardiac perfusion',
    ))
    vessels.append(dict(
        name='R. Coronary Artery',
        path=[(1, -5, 37), (-1, -3, 36), (-2, -5, 34), (-1, -7, 33)],
        radius=0.18,
        wss_range=(10, 70),
        group='Arterial',
        significance='Supplies heart muscle',
    ))

    # Pulmonary Trunk
    vessels.append(dict(
        name='Pulmonary Trunk',
        path=[(1, -3, 37), (3, -1, 39), (5, 0, 40)],
        radius=0.7,
        wss_range=(10, 30),
        group='Arterial',
        significance='Low-pressure pulmonary circulation; lower WSS than systemic',
    ))
    vessels.append(dict(
        name='R. Pulmonary Artery',
        path=[(5, 0, 40), (7, -1, 40), (9, -2, 39), (11, -3, 38)],
        radius=0.5,
        wss_range=(10, 30),
        group='Arterial',
        significance='To right lung',
    ))
    vessels.append(dict(
        name='L. Pulmonary Artery',
        path=[(5, 0, 40), (3, 1, 41), (-2, 0, 41), (-6, -1, 40), (-9, -2, 39)],
        radius=0.5,
        wss_range=(10, 30),
        group='Arterial',
        significance='To left lung',
    ))

    # Iliac Arteries → Femoral
    vessels.append(dict(
        name='R. Common Iliac',
        path=[(0, -5, -8), (3, -4.5, -12), (6, -4, -16)],
        radius=0.55,
        wss_range=(10, 70),
        group='Arterial',
        significance='Aortic bifurcation; disturbed flow at junction',
    ))
    vessels.append(dict(
        name='R. Femoral Artery',
        path=[(6, -4, -16), (7, -2, -22), (7.5, -1, -32), (8, 0, -42),
              (8, 0, -52), (8, 0, -60)],
        radius=0.4,
        wss_range=(10, 70),
        group='Arterial',
        significance='Major lower limb artery',
    ))
    vessels.append(dict(
        name='L. Common Iliac',
        path=[(0, -5, -8), (-3, -4.5, -12), (-6, -4, -16)],
        radius=0.55,
        wss_range=(10, 70),
        group='Arterial',
        significance='Aortic bifurcation',
    ))
    vessels.append(dict(
        name='L. Femoral Artery',
        path=[(-6, -4, -16), (-7, -2, -22), (-7.5, -1, -32), (-8, 0, -42),
              (-8, 0, -52), (-8, 0, -60)],
        radius=0.4,
        wss_range=(10, 70),
        group='Arterial',
        significance='Major lower limb artery',
    ))

    # ── VENOUS SYSTEM ──

    # Inferior Vena Cava
    vessels.append(dict(
        name='Inferior Vena Cava',
        path=[(2, -6, -8), (2, -6.5, -2), (2, -7, 5), (2, -7, 14),
              (2, -6.5, 22), (2.5, -6, 30), (3, -5, 35)],
        radius=1.3,
        wss_range=(1, 6),
        group='Venous',
        significance='WSS 1-6 dyne/cm\u00b2; low-pressure, high-capacitance return',
    ))

    # Superior Vena Cava
    vessels.append(dict(
        name='Superior Vena Cava',
        path=[(3, -5, 35), (4, -3, 40), (4.5, -2, 44), (4, -1, 48)],
        radius=1.1,
        wss_range=(1, 6),
        group='Venous',
        significance='WSS 1-6 dyne/cm\u00b2; drains upper body',
    ))

    # Right Jugular Vein
    vessels.append(dict(
        name='R. Jugular Vein',
        path=[(4, -1, 48), (5, -2, 52), (5, -2.5, 58), (4.5, -2, 64),
              (4, -1, 68)],
        radius=0.5,
        wss_range=(1, 6),
        group='Venous',
        significance='WSS 1-6 dyne/cm\u00b2; cerebral venous drainage',
    ))

    # Left Jugular Vein
    vessels.append(dict(
        name='L. Jugular Vein',
        path=[(4, -1, 48), (1, -2, 50), (-2, -2.5, 54), (-4, -2.5, 60),
              (-4, -2, 66), (-3.5, -1, 68)],
        radius=0.5,
        wss_range=(1, 6),
        group='Venous',
        significance='WSS 1-6 dyne/cm\u00b2; cerebral venous drainage',
    ))

    # Right Femoral Vein
    vessels.append(dict(
        name='R. Femoral Vein',
        path=[(9, -1, -58), (9, -1, -48), (9, -2, -38), (8.5, -3, -28),
              (7.5, -4, -18), (5, -5, -10), (2, -6, -8)],
        radius=0.45,
        wss_range=(1, 6),
        group='Venous',
        significance='WSS 1-6 dyne/cm\u00b2; lower limb venous return',
    ))

    # Left Femoral Vein
    vessels.append(dict(
        name='L. Femoral Vein',
        path=[(-9, -1, -58), (-9, -1, -48), (-9, -2, -38), (-8.5, -3, -28),
              (-7.5, -4, -18), (-5, -5, -10), (2, -6, -8)],
        radius=0.45,
        wss_range=(1, 6),
        group='Venous',
        significance='WSS 1-6 dyne/cm\u00b2; lower limb venous return',
    ))

    # Hepatic Veins
    vessels.append(dict(
        name='Hepatic Vein',
        path=[(8, -1, 22), (6, -3, 24), (4, -5, 27), (2.5, -6, 30)],
        radius=0.4,
        wss_range=(1, 6),
        group='Venous',
        significance='Drains liver sinusoids into IVC',
    ))

    # Portal Vein
    vessels.append(dict(
        name='Portal Vein',
        path=[(0, -3, 12), (2, -2, 14), (4, -1, 17), (7, 0, 20)],
        radius=0.5,
        wss_range=(1, 6),
        group='Venous',
        significance='Carries nutrient-rich blood to liver; moderate WSS',
    ))

    # Pulmonary Veins
    vessels.append(dict(
        name='R. Pulmonary Vein',
        path=[(10, -2, 37), (8, -3, 36), (5, -4, 35.5), (3, -5, 35)],
        radius=0.45,
        wss_range=(1, 6),
        group='Venous',
        significance='Returns oxygenated blood from lungs',
    ))
    vessels.append(dict(
        name='L. Pulmonary Vein',
        path=[(-8, -2, 38), (-5, -3, 37), (-2, -4, 36), (0, -5, 35.5)],
        radius=0.45,
        wss_range=(1, 6),
        group='Venous',
        significance='Returns oxygenated blood from lungs',
    ))

    # ── LYMPHATIC SYSTEM ──

    # Thoracic Duct (major lymphatic vessel)
    vessels.append(dict(
        name='Thoracic Duct',
        path=[(-1, -8, 0), (-1.5, -8.5, 8), (-2, -8.5, 18), (-2, -8, 28),
              (-2, -6, 38), (-2.5, -4, 44), (-3, -2, 47)],
        radius=0.15,
        wss_range=(0.1, 0.6),
        group='Lymphatic',
        significance='WSS 0.1-0.6 dyne/cm\u00b2; near-stagnant lymphatic flow',
    ))

    # Right Lymphatic Duct
    vessels.append(dict(
        name='R. Lymphatic Duct',
        path=[(3, -4, 44), (4, -3, 46), (4.5, -2, 47)],
        radius=0.12,
        wss_range=(0.1, 0.6),
        group='Lymphatic',
        significance='WSS 0.1-0.6 dyne/cm\u00b2; drains right upper body',
    ))

    # ── ARTERIOLES (very thin, high WSS) ──

    vessels.append(dict(
        name='Renal Arteriole',
        path=[(9, -2, 15), (10.5, -1, 15.5), (12, -0.5, 16)],
        radius=0.08,
        wss_range=(40, 60),
        group='Arteriolar',
        significance='WSS ~55 dyne/cm\u00b2; narrow diameter creates high shear',
    ))
    vessels.append(dict(
        name='Hepatic Arteriole',
        path=[(8, 0, 22), (9.5, 0.5, 22.5), (11, 1, 22)],
        radius=0.08,
        wss_range=(40, 60),
        group='Arteriolar',
        significance='WSS ~55 dyne/cm\u00b2; transitions to sinusoidal bed',
    ))
    vessels.append(dict(
        name='Mesenteric Arteriole',
        path=[(0, -4, 6), (2, -2, 5), (4, -1, 4)],
        radius=0.08,
        wss_range=(40, 60),
        group='Arteriolar',
        significance='WSS ~55 dyne/cm\u00b2; supplies intestinal microcirculation',
    ))

    return vessels


# =============================================================================
# SECTION 5: Rendering Functions
# =============================================================================

# Track colors for legend display
GROUP_COLORS = {
    'Arterial': 'rgb(230, 60, 30)',
    'Venous': 'rgb(40, 100, 220)',
    'Lymphatic': 'rgb(20, 50, 150)',
    'Arteriolar': 'rgb(255, 150, 0)',
    'Sinusoidal': 'rgb(10, 20, 120)',
    'Pathological': 'rgb(255, 255, 0)',
}

_legend_shown = set()


def render_tube_vessel(vessel, show_colorbar=False):
    """Render a single vessel as a colored tube mesh."""
    result = generate_tube_mesh(vessel['path'], vessel['radius'])
    if result is None:
        return None

    x, y, z, fi, fj, fk = result
    n_verts = len(x)

    # Compute WSS intensity (log scale, uniform per vessel)
    wss_mean = np.mean(vessel['wss_range'])
    log_wss = np.log10(max(wss_mean, 0.01))
    intensity = np.full(n_verts, log_wss)

    # Build hover text
    wss_lo, wss_hi = vessel['wss_range']
    hover = (
        f"<b>{vessel['name']}</b><br>"
        f"WSS: {wss_lo}\u2013{wss_hi} dyne/cm\u00b2<br>"
        f"Region: {vessel['group']}<br>"
        f"<i>{vessel['significance']}</i>"
    )
    hovertext = [hover] * n_verts

    group = vessel['group']
    show_legend = group not in _legend_shown
    if show_legend:
        _legend_shown.add(group)

    colorbar_cfg = None
    if show_colorbar:
        colorbar_cfg = dict(
            title=dict(
                text='Wall Shear Stress<br>(dyne/cm\u00b2)',
                font=dict(color='white', size=12),
                side='right',
            ),
            tickvals=COLORBAR_TICKVALS,
            ticktext=COLORBAR_TICKTEXT,
            tickfont=dict(color='white', size=11),
            len=0.6,
            x=1.02,
            y=0.5,
            bgcolor='rgba(0,0,0,0.3)',
            bordercolor='rgba(255,255,255,0.2)',
            borderwidth=1,
            thickness=18,
        )

    trace = go.Mesh3d(
        x=x, y=y, z=z,
        i=fi, j=fj, k=fk,
        intensity=intensity,
        colorscale=WSS_COLORSCALE,
        cmin=WSS_LOG_MIN,
        cmax=WSS_LOG_MAX,
        colorbar=colorbar_cfg,
        hovertext=hovertext,
        hoverinfo='text',
        name=group,
        legendgroup=group,
        showlegend=show_legend,
        flatshading=False,
        lighting=dict(ambient=0.5, diffuse=0.7, specular=0.3, roughness=0.4),
        lightposition=dict(x=50, y=50, z=100),
    )
    return trace


def render_capillary_bed(center, spread, wss_range, name, significance, group,
                         n_points=120, marker_size=2.5):
    """Render a microvascular bed as a scatter cloud of small points."""
    cx, cy, cz = center
    np.random.seed(hash(name) % 2**31)

    # Random points in an ellipsoidal volume
    theta = np.random.uniform(0, 2 * np.pi, n_points)
    phi = np.random.uniform(0, np.pi, n_points)
    r = np.random.uniform(0.2, 1.0, n_points) ** (1/3)  # uniform volume
    sx, sy, sz = spread if isinstance(spread, (list, tuple)) else (spread, spread, spread)

    x = cx + r * sx * np.sin(phi) * np.cos(theta)
    y = cy + r * sy * np.sin(phi) * np.sin(theta)
    z = cz + r * sz * np.cos(phi)

    wss_mean = np.mean(wss_range)
    log_wss = np.log10(max(wss_mean, 0.01))
    wss_lo, wss_hi = wss_range

    # Vary intensity slightly for visual interest
    intensity = log_wss + np.random.uniform(-0.15, 0.15, n_points)

    hover = (
        f"<b>{name}</b><br>"
        f"WSS: {wss_lo}\u2013{wss_hi} dyne/cm\u00b2<br>"
        f"<i>{significance}</i>"
    )

    show_legend = group not in _legend_shown
    if show_legend:
        _legend_shown.add(group)

    return go.Scatter3d(
        x=x, y=y, z=z,
        mode='markers',
        marker=dict(
            size=marker_size,
            color=intensity,
            colorscale=WSS_COLORSCALE,
            cmin=WSS_LOG_MIN,
            cmax=WSS_LOG_MAX,
            opacity=0.7,
            showscale=False,
        ),
        hovertext=[hover] * n_points,
        hoverinfo='text',
        name=group,
        legendgroup=group,
        showlegend=show_legend,
    )


def render_pathological_marker(center, wss_range, name, significance, symbol='diamond',
                               marker_size=10, color='yellow'):
    """Render a pathological hotspot as a prominent marker."""
    cx, cy, cz = center
    wss_lo, wss_hi = wss_range

    wss_text = f"{wss_lo}\u2013{wss_hi}" if wss_hi < 5000 else f">{wss_lo}"
    hover = (
        f"<b>\u26a0 {name}</b><br>"
        f"WSS: {wss_text} dyne/cm\u00b2<br>"
        f"<b>PATHOLOGICAL</b><br>"
        f"<i>{significance}</i>"
    )

    show_legend = 'Pathological' not in _legend_shown
    if show_legend:
        _legend_shown.add('Pathological')

    return go.Scatter3d(
        x=[cx], y=[cy], z=[cz],
        mode='markers+text',
        marker=dict(
            size=marker_size,
            color=color,
            symbol=symbol,
            opacity=0.95,
            line=dict(width=1, color='white'),
        ),
        text=[name],
        textposition='top center',
        textfont=dict(color=color, size=9, family='Arial Black'),
        hovertext=[hover],
        hoverinfo='text',
        name='Pathological',
        legendgroup='Pathological',
        showlegend=show_legend,
    )


def render_heart():
    """Render the heart as a stylized mesh."""
    # Generate a slightly elongated sphere for the heart
    n = 20
    phi = np.linspace(0, np.pi, n)
    theta = np.linspace(0, 2 * np.pi, n)
    phi, theta = np.meshgrid(phi, theta)

    # Heart center and dimensions
    cx, cy, cz = 1, -5, 35
    rx, ry, rz = 3.5, 3, 4.5

    x = (cx + rx * np.sin(phi) * np.cos(theta)).flatten()
    y = (cy + ry * np.sin(phi) * np.sin(theta)).flatten()
    z = (cz + rz * np.cos(phi)).flatten()

    hover = (
        "<b>\u2764 Heart</b><br>"
        "Central pump of the circulatory system<br>"
        "Generates pulsatile flow driving WSS throughout vasculature"
    )

    return go.Mesh3d(
        x=x, y=y, z=z,
        alphahull=0,
        opacity=0.55,
        color='rgb(180, 30, 30)',
        hovertext=[hover] * len(x),
        hoverinfo='text',
        name='Heart',
        legendgroup='Heart',
        showlegend=True,
        flatshading=False,
        lighting=dict(ambient=0.6, diffuse=0.6, specular=0.2),
    )


# =============================================================================
# SECTION 6: Organ Markers
# =============================================================================

def render_organ_markers():
    """Add subtle markers for key organs referenced in the manuscript."""
    organs = [
        ((9, -1, 20), 'Liver', 'Key clearance organ; contains sinusoidal beds (WSS 0.1-0.6)'),
        ((10, -2, 15), 'R. Kidney', 'High-flow filtration organ'),
        ((-10, -2, 16), 'L. Kidney', 'High-flow filtration organ'),
        ((-10, -1, 17), 'Spleen', 'Filtration slits test NP deformability'),
        ((9, -2, 37), 'R. Lung', 'Pulmonary capillary bed'),
        ((-9, -2, 38), 'L. Lung', 'Pulmonary capillary bed'),
    ]

    x = [o[0][0] for o in organs]
    y = [o[0][1] for o in organs]
    z = [o[0][2] for o in organs]
    texts = [o[1] for o in organs]
    hovers = [f"<b>{o[1]}</b><br><i>{o[2]}</i>" for o in organs]

    return go.Scatter3d(
        x=x, y=y, z=z,
        mode='markers+text',
        marker=dict(size=5, color='rgba(150, 200, 255, 0.5)', symbol='circle',
                    line=dict(width=0.5, color='rgba(200,220,255,0.6)')),
        text=texts,
        textposition='middle right',
        textfont=dict(color='rgba(180, 210, 240, 0.7)', size=8),
        hovertext=hovers,
        hoverinfo='text',
        name='Organs',
        legendgroup='Organs',
        showlegend=True,
    )


# =============================================================================
# SECTION 7: Figure Assembly
# =============================================================================

def build_figure():
    """Assemble all components into the final Plotly figure."""
    fig = go.Figure()

    # 1. Body outline (back layer)
    for trace in create_body_outline():
        fig.add_trace(trace)

    # 2. Heart
    fig.add_trace(render_heart())

    # 3. All vessels
    vessels = define_vessels()
    for idx, vessel in enumerate(vessels):
        trace = render_tube_vessel(vessel, show_colorbar=(idx == 0))
        if trace is not None:
            fig.add_trace(trace)

    # 4. Capillary / sinusoidal beds
    fig.add_trace(render_capillary_bed(
        center=(9, 0, 21), spread=(3.5, 2.5, 3), wss_range=(0.1, 0.6),
        name='Hepatic Sinusoidal Bed', group='Sinusoidal',
        significance='WSS 0.1-0.6 dyne/cm\u00b2; ultra-low shear allows NP margination;\nfenestrated endothelium enables NP access',
        n_points=200, marker_size=2,
    ))

    fig.add_trace(render_capillary_bed(
        center=(5, 2, 38), spread=(2, 1.5, 2), wss_range=(0.5, 3),
        name='Tumor Vasculature', group='Pathological',
        significance='Low & oscillatory WSS; chaotic architecture;\nelevated interstitial pressure impairs NP penetration',
        n_points=100, marker_size=2.5,
    ))

    # 5. Pathological markers
    fig.add_trace(render_pathological_marker(
        center=(3.5, -1, 62), wss_range=(0.5, 4),
        name='Atherosclerotic\nPlaque Site',
        significance='WSS <4 dyne/cm\u00b2; low/oscillatory shear promotes\nendothelial dysfunction and plaque formation;\nupregulates VCAM-1 and ICAM-1',
        symbol='diamond', color='rgb(255, 220, 50)', marker_size=9,
    ))

    fig.add_trace(render_pathological_marker(
        center=(3, -0.5, 57), wss_range=(100, 5000),
        name='Stenotic\nHotspot',
        significance='WSS >1000 dyne/cm\u00b2; extreme shear strips\nhydration shells and ruptures soft lipid bilayers;\ncauses premature burst release',
        symbol='diamond', color='rgb(255, 50, 50)', marker_size=9,
    ))

    # 6. Organ markers
    fig.add_trace(render_organ_markers())

    # ── LAYOUT ──
    fig.update_layout(
        scene=dict(
            xaxis=dict(visible=False, range=[-35, 35]),
            yaxis=dict(visible=False, range=[-15, 15]),
            zaxis=dict(visible=False, range=[-90, 90]),
            bgcolor='rgb(12, 12, 22)',
            camera=dict(
                eye=dict(x=2.0, y=1.0, z=0.2),
                up=dict(x=0, y=0, z=1),
                center=dict(x=0, y=0, z=0),
            ),
            aspectmode='data',
        ),
        paper_bgcolor='rgb(12, 12, 22)',
        plot_bgcolor='rgb(12, 12, 22)',
        title=dict(
            text=(
                '<b>Wall Shear Stress Distribution in the Human Circulatory System</b>'
                '<br><sup style="color:rgb(140,160,180)">Interactive 3D Visualization '
                '| Data: Modh et al., ACS Nano (2025)</sup>'
            ),
            font=dict(color='white', size=17, family='Arial'),
            x=0.5,
            xanchor='center',
            y=0.97,
        ),
        width=1300,
        height=900,
        margin=dict(l=0, r=80, t=60, b=30),
        showlegend=True,
        legend=dict(
            font=dict(color='rgb(200, 210, 220)', size=11),
            bgcolor='rgba(20, 20, 35, 0.8)',
            bordercolor='rgba(100, 120, 150, 0.3)',
            borderwidth=1,
            x=0.01,
            y=0.99,
            xanchor='left',
            yanchor='top',
            itemclick='toggle',
            itemdoubleclick='toggleothers',
            title=dict(
                text='<b>Vessel Groups</b>',
                font=dict(color='rgb(180, 200, 220)', size=11),
            ),
        ),
        annotations=[
            dict(
                text=(
                    '\U0001f5b1 Rotate: drag | Zoom: scroll | '
                    'Hover: WSS data | Legend: toggle groups'
                ),
                xref='paper', yref='paper',
                x=0.5, y=0.01,
                showarrow=False,
                font=dict(color='rgb(100, 120, 140)', size=10),
            ),
        ],
    )

    return fig


# =============================================================================
# SECTION 8: Export
# =============================================================================

def main():
    """Generate and export the interactive 3D visualization."""
    print('Building 3D circulatory system visualization...')

    fig = build_figure()

    # Ensure output directory exists
    os.makedirs('docs', exist_ok=True)

    output_path = os.path.join('docs', 'index.html')

    fig.write_html(
        output_path,
        include_plotlyjs='cdn',
        full_html=True,
        config=dict(
            displayModeBar=True,
            modeBarButtonsToRemove=['lasso2d', 'select2d'],
            displaylogo=False,
            toImageButtonOptions=dict(
                format='png',
                filename='wss_circulatory_system',
                height=1200,
                width=1600,
                scale=2,
            ),
        ),
    )

    file_size = os.path.getsize(output_path) / 1024
    print(f'Visualization exported to {output_path} ({file_size:.0f} KB)')
    print(f'Open in browser: file://{os.path.abspath(output_path)}')


if __name__ == '__main__':
    main()
