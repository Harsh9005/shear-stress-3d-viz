#!/usr/bin/env python3
"""
build_data.py — single source of truth for The Hemodynamic Landscape.

Defines the circulatory geometry, wall-shear-stress (WSS) bands, pathological scenarios,
the nanoparticle-journey waypoints, the quantitative-panel data, and the WSS colorscale —
then serialises them ONCE to docs/data/data.json and re-emits that exact JSON as an ES module
docs/data/data.js (export const DATA = ...). The web app imports data.js; the static-figure
generator reads data.json. No value is hand-written twice.

All WSS values are in dyne/cm² and are representative magnitudes consistent with the
hemodynamics & nanomedicine literature; every value used in scenarios/journey/panels is checked
against build/allowed_wss.py. Vessel notes never restate a WSS number — tooltips compose the
range from the `wss` field at render time.

Run:  python3 build/build_data.py
"""

import json
import os
import re
import math

from allowed_wss import (
    ALLOWED_WSS, FORBIDDEN_NUMBERS, REGIME_BINS, SHEAR_GAP, SPECTRUM_MARKERS, is_allowed,
)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "docs", "data"))

LOG_MIN = -1.0   # log10(0.1)
LOG_MAX = 3.0    # log10(1000)

# ---------------------------------------------------------------------------
# Colorscale — the SOLE declared stop<->wss<->rgb mapping (web + legend + matplotlib).
# stop = (log10(wss) - LOG_MIN) / (LOG_MAX - LOG_MIN)
# ---------------------------------------------------------------------------
COLORSCALE = [
    {"wss": 0.1,  "rgb": [10, 20, 120]},    # sinusoids — deep blue
    {"wss": 0.5,  "rgb": [0, 100, 220]},    # blue
    {"wss": 1.0,  "rgb": [0, 180, 220]},    # veins — cyan
    {"wss": 3.0,  "rgb": [0, 200, 80]},     # green
    {"wss": 10.0, "rgb": [220, 220, 0]},    # normal arteries — yellow
    {"wss": 30.0, "rgb": [255, 150, 0]},    # orange
    {"wss": 100.0, "rgb": [230, 30, 0]},    # red
    {"wss": 300.0, "rgb": [200, 0, 100]},   # magenta
    {"wss": 1000.0, "rgb": [160, 0, 200]},  # severe stenosis — purple
]


def _stop(wss):
    return (math.log10(wss) - LOG_MIN) / (LOG_MAX - LOG_MIN)


def regime_for(mean_wss):
    if mean_wss < 1.0:
        return "extreme"        # near-stagnant (sinusoids / lymphatics)
    if mean_wss < REGIME_BINS["low"]:
        return "low"
    if mean_wss <= REGIME_BINS["moderate"]:
        return "moderate"
    return "high"


def slug(name):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


# ---------------------------------------------------------------------------
# Vessels — anatomically-approximate centerlines (cm). Notes carry NO WSS digits.
# (name, [path], radius, (wss_lo, wss_hi), group, note)
# ---------------------------------------------------------------------------
_VESSELS = [
    ("Ascending Aorta", [(1,-5,35),(1.5,-3,38),(2,-1,42),(2,1,46)], 1.4, (10,70), "Arterial",
     "Main conduit from the heart; high pulsatile flow"),
    ("Aortic Arch", [(2,1,46),(1,2,48),(-1,1,49),(-2,-2,47),(-2,-4,45)], 1.3, (10,70), "Arterial",
     "Curved region; disturbed flow at branch points"),
    ("Descending Aorta", [(-2,-4,45),(-1.5,-5,40),(-1,-6,32),(-0.5,-6,22),(0,-6,12),(0,-5.5,2),(0,-5,-8)],
     1.1, (10,70), "Arterial", "Thoraco-abdominal conduit; sustained arterial shear"),
    ("R. Common Carotid", [(2,1,46),(3,0,50),(3.5,-1,55),(3.5,-1,60),(3,0,65),(2.5,0,70)], 0.4, (10,20),
     "Arterial", "Bifurcation is an atherosclerosis-prone site"),
    ("L. Common Carotid", [(0,1,48),(-2,0,52),(-3,-0.5,56),(-3.5,-0.5,61),(-3,0,66),(-2.5,0,70)], 0.4,
     (10,20), "Arterial", "Laminar flow favours an anti-inflammatory endothelium"),
    ("R. Subclavian Artery", [(2,1,46),(6,0,47),(10,-1,46),(15,-1,44)], 0.45, (10,70), "Arterial",
     "Supplies the right upper limb"),
    ("R. Brachial Artery", [(15,-1,44),(18,-1,40),(20,-1,34),(21,0,26),(22,0,18),(23,0,10)], 0.3, (10,70),
     "Arterial", "Upper-limb arterial supply"),
    ("L. Subclavian Artery", [(-1,1,48),(-6,0,47),(-10,-1,46),(-15,-1,44)], 0.45, (10,70), "Arterial",
     "Supplies the left upper limb"),
    ("L. Brachial Artery", [(-15,-1,44),(-18,-1,40),(-20,-1,34),(-21,0,26),(-22,0,18),(-23,0,10)], 0.3,
     (10,70), "Arterial", "Upper-limb arterial supply"),
    ("Hepatic Artery", [(0,-5.5,20),(2,-3,20),(5,-1,21),(8,0,22)], 0.3, (10,70), "Arterial",
     "Supplies the liver; branches into hepatic sinusoids"),
    ("Splenic Artery", [(0,-5.5,20),(-2,-3,19),(-5,-2,18),(-9,-1,17)], 0.25, (10,70), "Arterial",
     "Supplies the spleen; tortuosity creates oscillatory shear"),
    ("R. Renal Artery", [(0,-5.5,14),(3,-4,14),(6,-3,14.5),(9,-2,15)], 0.35, (10,70), "Arterial",
     "Supplies the right kidney; a high-flow, high-shear organ"),
    ("L. Renal Artery", [(0,-5.5,15),(-3,-4,15),(-6,-3,15.5),(-9,-2,16)], 0.35, (10,70), "Arterial",
     "Supplies the left kidney"),
    ("L. Coronary Artery", [(1,-5,37),(3,-3,36),(4,-4,34),(3,-6,33)], 0.18, (10,70), "Arterial",
     "Supplies heart muscle; critical for cardiac perfusion"),
    ("R. Coronary Artery", [(1,-5,37),(-1,-3,36),(-2,-5,34),(-1,-7,33)], 0.18, (10,70), "Arterial",
     "Supplies heart muscle"),
    ("Pulmonary Trunk", [(1,-3,37),(3,-1,39),(5,0,40)], 0.7, (10,30), "Arterial",
     "Low-pressure pulmonary circulation; lower shear than the systemic side"),
    ("R. Pulmonary Artery", [(5,0,40),(7,-1,40),(9,-2,39),(11,-3,38)], 0.5, (10,30), "Arterial",
     "Carries blood to the right lung"),
    ("L. Pulmonary Artery", [(5,0,40),(3,1,41),(-2,0,41),(-6,-1,40),(-9,-2,39)], 0.5, (10,30), "Arterial",
     "Carries blood to the left lung"),
    ("R. Common Iliac", [(0,-5,-8),(3,-4.5,-12),(6,-4,-16)], 0.55, (10,70), "Arterial",
     "Aortic bifurcation; disturbed flow at the junction"),
    ("R. Femoral Artery", [(6,-4,-16),(7,-2,-22),(7.5,-1,-32),(8,0,-42),(8,0,-52),(8,0,-60)], 0.4, (10,70),
     "Arterial", "Major lower-limb artery"),
    ("L. Common Iliac", [(0,-5,-8),(-3,-4.5,-12),(-6,-4,-16)], 0.55, (10,70), "Arterial",
     "Aortic bifurcation"),
    ("L. Femoral Artery", [(-6,-4,-16),(-7,-2,-22),(-7.5,-1,-32),(-8,0,-42),(-8,0,-52),(-8,0,-60)], 0.4,
     (10,70), "Arterial", "Major lower-limb artery"),
    # Venous
    ("Inferior Vena Cava", [(2,-6,-8),(2,-6.5,-2),(2,-7,5),(2,-7,14),(2,-6.5,22),(2.5,-6,30),(3,-5,35)], 1.3,
     (1,6), "Venous", "Low-pressure, high-capacitance venous return"),
    ("Superior Vena Cava", [(3,-5,35),(4,-3,40),(4.5,-2,44),(4,-1,48)], 1.1, (1,6), "Venous",
     "Drains the upper body"),
    ("R. Jugular Vein", [(4,-1,48),(5,-2,52),(5,-2.5,58),(4.5,-2,64),(4,-1,68)], 0.5, (1,6), "Venous",
     "Cerebral venous drainage"),
    ("L. Jugular Vein", [(4,-1,48),(1,-2,50),(-2,-2.5,54),(-4,-2.5,60),(-4,-2,66),(-3.5,-1,68)], 0.5, (1,6),
     "Venous", "Cerebral venous drainage"),
    ("R. Femoral Vein", [(9,-1,-58),(9,-1,-48),(9,-2,-38),(8.5,-3,-28),(7.5,-4,-18),(5,-5,-10),(2,-6,-8)],
     0.45, (1,6), "Venous", "Lower-limb venous return"),
    ("L. Femoral Vein", [(-9,-1,-58),(-9,-1,-48),(-9,-2,-38),(-8.5,-3,-28),(-7.5,-4,-18),(-5,-5,-10),(2,-6,-8)],
     0.45, (1,6), "Venous", "Lower-limb venous return"),
    ("Hepatic Vein", [(8,-1,22),(6,-3,24),(4,-5,27),(2.5,-6,30)], 0.4, (1,6), "Venous",
     "Drains liver sinusoids into the inferior vena cava"),
    ("Portal Vein", [(0,-3,12),(2,-2,14),(4,-1,17),(7,0,20)], 0.5, (1,6), "Venous",
     "Carries nutrient-rich blood to the liver"),
    ("R. Pulmonary Vein", [(10,-2,37),(8,-3,36),(5,-4,35.5),(3,-5,35)], 0.45, (1,6), "Venous",
     "Returns oxygenated blood from the lungs"),
    ("L. Pulmonary Vein", [(-8,-2,38),(-5,-3,37),(-2,-4,36),(0,-5,35.5)], 0.45, (1,6), "Venous",
     "Returns oxygenated blood from the lungs"),
    # Lymphatic
    ("Thoracic Duct", [(-1,-8,0),(-1.5,-8.5,8),(-2,-8.5,18),(-2,-8,28),(-2,-6,38),(-2.5,-4,44),(-3,-2,47)],
     0.15, (0.1,0.6), "Lymphatic", "Near-stagnant lymphatic flow"),
    ("R. Lymphatic Duct", [(3,-4,44),(4,-3,46),(4.5,-2,47)], 0.12, (0.1,0.6), "Lymphatic",
     "Drains the right upper body"),
    # Arteriolar
    ("Renal Arteriole", [(9,-2,15),(10.5,-1,15.5),(12,-0.5,16)], 0.08, (40,60), "Arteriolar",
     "Narrow diameter creates high shear"),
    ("Hepatic Arteriole", [(8,0,22),(9.5,0.5,22.5),(11,1,22)], 0.08, (40,60), "Arteriolar",
     "Transitions into the low-shear sinusoidal bed"),
    ("Mesenteric Arteriole", [(0,-4,6),(2,-2,5),(4,-1,4)], 0.08, (40,60), "Arteriolar",
     "Supplies the intestinal microcirculation"),
]

GROUP_COLORS = {
    "Arterial": [230, 60, 30], "Venous": [40, 100, 220], "Lymphatic": [20, 50, 150],
    "Arteriolar": [255, 150, 0],
}


# ---------------------------------------------------------------------------
# Real anatomy, produced offline by build/anatomy/ from BodyParts3D (CC BY-SA 2.1 Japan).
# Absent, everything below falls back to the hand-drawn geometry, so the data layer still
# builds on a clean checkout before the anatomy pipeline has been run.
# ---------------------------------------------------------------------------
ANATOMY_PATH = os.path.join(HERE, "anatomy", "vessels.json")


def load_anatomy():
    if not os.path.exists(ANATOMY_PATH):
        return {}
    with open(ANATOMY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


ANATOMY = load_anatomy()

# The authored radii are about half of life size: at the fitted 5.78 mm per scene unit, the
# ascending aorta's 1.4 would be a 16 mm vessel where a real one is near 30 mm. Now that the
# vessels sit inside a real body at a real scale, that undersizing reads as thin threads. One
# documented factor brings the whole tree to roughly life size rather than 37 hand edits.
# Geometry only — no WSS value depends on it.
RADIUS_SCALE = 1.8


def build_vessels():
    """
    Vessel geometry, preferring real anatomy over the hand-drawn placeholder paths.

    Every vessel carries a `provenance`: "anatomical" means the centerline was extracted from
    the segmented cadaver mesh named in `source`; "schematic" means this source has no such
    vessel (it segments no limb arteries, no cerebral arteries, no portal or hepatic vein and no
    lymphatics) and the path is authored — for the limbs, seated inside the real limb by
    build/anatomy/limbs.py. WSS values are untouched by any of this.
    """
    anat = ANATOMY.get("vessels", {})
    limbs = ANATOMY.get("limbPaths", {})
    out = []
    for name, path, radius, wss, group, note in _VESSELS:
        vid = slug(name)
        lo, hi = wss
        mean = (lo + hi) / 2.0
        entry = {
            "id": vid, "name": name, "group": group,
            "radius": round(float(radius) * RADIUS_SCALE, 3), "wss": [float(lo), float(hi)],
            "regime": regime_for(mean), "note": note,
        }
        if vid in anat:
            entry["path"] = [[float(a) for a in p] for p in anat[vid]["path"]]
            entry["provenance"] = "anatomical"
            entry["source"] = anat[vid]["sourceName"]
        elif vid in limbs:
            entry["path"] = [[float(a) for a in p] for p in limbs[vid]]
            entry["provenance"] = "schematic"
        else:
            entry["path"] = [[float(a) for a in p] for p in path]
            entry["provenance"] = "schematic"
        out.append(entry)
    return out


def vessel_point(vessels, vessel_id, t_along):
    """
    A point a fraction `t_along` down a vessel's centerline.

    Hotspots and lab targets are anchored this way rather than by absolute coordinates so that
    re-deriving a vessel's path moves everything attached to it. The previous absolute
    coordinates silently desynchronised the moment any path changed.
    """
    v = next((x for x in vessels if x["id"] == vessel_id), None)
    if v is None:
        raise KeyError(f"unknown vessel id: {vessel_id}")
    pts = v["path"]
    if len(pts) == 1:
        return list(pts[0])
    seg = []
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        seg.append(d)
        total += d
    if total <= 0:
        return list(pts[0])
    target = max(0.0, min(1.0, float(t_along))) * total
    run = 0.0
    for i, d in enumerate(seg):
        if run + d >= target or i == len(seg) - 1:
            f = 0.0 if d == 0 else (target - run) / d
            a, b = pts[i], pts[i + 1]
            return [round(a[k] + (b[k] - a[k]) * f, 3) for k in range(3)]
        run += d
    return list(pts[-1])


# Capillary / sinusoidal beds (point clouds) — the low-shear extreme.
# Beds are anchored to the organ they sit in, so the point cloud follows the real organ mesh
# rather than a coordinate typed next to it.
_BEDS = [
    ("Hepatic Sinusoidal Bed", "liver", (9, 0, 21), (3.5, 2.5, 3), (0.1, 0.6),
     "Ultra-low shear lets nanoparticles marginate; fenestrated endothelium allows access"),
]


def build_beds():
    out = []
    for name, organ_id, center, spread, wss, note in _BEDS:
        lo, hi = wss
        out.append({
            "id": slug(name), "name": name, "organ": organ_id,
            "center": organ_center(organ_id, center),
            "spread": list(map(float, spread)), "wss": [float(lo), float(hi)],
            "regime": regime_for((lo + hi) / 2.0), "note": note,
        })
    return out


# Organs. `id` matches the node names in docs/assets/anatomy/organs.glb, so the mesh, the
# tooltip note and any bed or tumor anchored to the organ all resolve through one key. Positions
# are the real mesh centroids when the anatomy pipeline has run; the fallbacks below are the old
# hand-placed values and are only used on a checkout without built assets.
_ORGANS = [
    ("liver", "Liver", (9, -1, 20), "Key clearance organ; contains low-shear sinusoidal beds"),
    ("right_kidney", "R. Kidney", (10, -2, 15), "High-flow filtration organ"),
    ("left_kidney", "L. Kidney", (-10, -2, 16), "High-flow filtration organ"),
    ("spleen", "Spleen", (-10, -1, 17), "Filtration slits test nanoparticle deformability"),
    ("right_lung", "R. Lung", (9, -2, 37), "Pulmonary capillary bed"),
    ("left_lung", "L. Lung", (-9, -2, 38), "Pulmonary capillary bed"),
    ("brain", "Brain", (0, 0, 66), "Behind the blood-brain barrier; carrier access is limited"),
    ("pancreas", "Pancreas", (0, -4, 8), "Dense stroma raises interstitial pressure"),
]


def organ_center(organ_id, fallback):
    """Real mesh centroid where available, else the hand-placed position."""
    o = ANATOMY.get("organs", {}).get(organ_id)
    return [float(c) for c in o["centroid"]] if o else [float(c) for c in fallback]


def build_organs():
    return [
        {"id": oid, "name": name, "pos": organ_center(oid, pos), "note": note}
        for oid, name, pos, note in _ORGANS
    ]


def build_landmarks():
    heart = ANATOMY.get("heart")
    out = {
        "heart": {"pos": heart["center"] if heart else [1.0, -5.0, 35.0],
                  "radii": [c / 2 for c in heart["extents"]] if heart else [3.5, 3.0, 4.5]},
    }
    if ANATOMY.get("bodyBounds"):
        out["body"] = {"bounds": ANATOMY["bodyBounds"]}
    return out


# ---------------------------------------------------------------------------
# Scenarios — honest framing (deny-list enforced). No fabricated %s, no per-site magnitudes.
# ---------------------------------------------------------------------------
ATHERO_VESSELS = ["r_common_carotid", "l_common_carotid", "aortic_arch",
                  "r_common_iliac", "l_common_iliac", "l_coronary_artery", "r_coronary_artery"]
STENOSIS_VESSELS = ["r_common_carotid", "l_common_iliac", "descending_aorta"]

# Hotspots are anchored to (vessel, fraction along it) and their coordinates are derived at
# build time. They used to be absolute positions typed next to the old hand-drawn paths, which
# meant any change to a vessel's course left them floating somewhere in the body with nothing to
# mark. Anchoring them makes that failure impossible.
ATHERO_ANCHORS = [
    ("r_common_carotid", 0.15, "Plaque", "plaque"),      # carotid bifurcation, atheroprone
    ("l_common_carotid", 0.15, "Plaque", "plaque"),
    ("aortic_arch", 0.55, "Arch plaque", "plaque"),      # inner curvature of the arch
]
STENOSIS_ANCHORS = [
    ("r_common_carotid", 0.30, "Stenosis", "stenosis"),
    ("l_common_iliac", 0.45, "Stenosis", "stenosis"),
    ("descending_aorta", 0.60, "Stenosis", "stenosis"),
]


def build_hotspots(vessels, anchors):
    return [
        {"pos": vessel_point(vessels, vid, t), "vesselId": vid, "tAlong": t,
         "label": label, "kind": kind}
        for vid, t, label, kind in anchors
    ]
def build_scenarios(vessels):
    athero_hotspots = build_hotspots(vessels, ATHERO_ANCHORS)
    stenosis_hotspots = build_hotspots(vessels, STENOSIS_ANCHORS)
    athero_change = {
        "vessels": ATHERO_VESSELS, "provenance": "literature", "regime": "low_oscillatory",
        "displayWss": [0.5, 4.0], "openEnded": False,
    }
    stenosis_change = {
        "vessels": STENOSIS_VESSELS, "provenance": "literature", "regime": "extreme",
        "displayWss": None, "sentinel": 1000.0, "openEnded": True,
    }
    return [
        {"id": "healthy", "label": "Healthy baseline",
         "blurb": "Across a healthy circulation, wall shear stress spans four orders of magnitude — "
                  "from near-stagnant hepatic sinusoids to the fast arterial tree. A circulating "
                  "nanocarrier must survive this entire range.",
         "changes": [], "hotspots": [], "beds": [], "dim": False},
        {"id": "atherosclerosis", "label": "Atherosclerosis",
         "blurb": "Plaque forms where shear is low and oscillatory (below ~4 dyne/cm²) — typically at "
                  "bifurcations. Disturbed flow drives a pro-inflammatory endothelium that upregulates "
                  "VCAM-1 and ICAM-1, which double as nanoparticle adhesion targets.",
         "changes": [athero_change], "hotspots": athero_hotspots, "beds": [], "dim": True},
        {"id": "stenosis", "label": "Arterial stenosis",
         "blurb": "Severe narrowing creates shear hotspots above 1000 dyne/cm² — extreme stress that can "
                  "strip a carrier's hydration shell and rupture soft lipid bilayers, causing premature "
                  "burst release before the target is reached.",
         "changes": [stenosis_change], "hotspots": stenosis_hotspots, "beds": [], "dim": True},
        {"id": "combined", "label": "Combined pathology",
         "blurb": "Co-existing atherosclerosis and stenosis in one patient — and you can layer tumors at "
                  "any site on top, for the full hemodynamic range a carrier must survive.",
         "changes": [athero_change, stenosis_change],
         "hotspots": athero_hotspots + stenosis_hotspots, "beds": [], "dim": True},
    ]


# ---------------------------------------------------------------------------
# Tumor sites — a combinable layer (toggled independently of the disease scenarios).
# Each site is the honest low/oscillatory regime; representativeWss is for colour only
# (schematic), notes are qualitative with NO digits-as-WSS, and nearVessels recolour locally.
# ---------------------------------------------------------------------------
# Sites are anchored to the organ they occur in: `pos` is that organ's real mesh centroid, so a
# tumor overlay lands inside the organ instead of at a coordinate typed beside it. The coordinate
# in each row is only the fallback for a checkout with no built anatomy.
_TUMOR_SITES = [
    ("Brain", "brain", [0, 0, 66], [3.0, 3.0, 3.5],
     "Glioblastoma neovasculature is chaotic and leaky; the blood-brain barrier limits carrier access.",
     ["r_common_carotid", "l_common_carotid", "r_jugular_vein", "l_jugular_vein"]),
    ("Right lung", "right_lung", [9, -2, 37], [2.6, 2.0, 2.8],
     "Pulmonary tumor vessels are tortuous with low, oscillatory shear; first-pass capillary trapping affects carriers.",
     ["r_pulmonary_artery", "r_pulmonary_vein"]),
    ("Left lung", "left_lung", [-9, -2, 38], [2.6, 2.0, 2.8],
     "Pulmonary tumor vessels are tortuous with low, oscillatory shear; first-pass capillary trapping affects carriers.",
     ["l_pulmonary_artery", "l_pulmonary_vein"]),
    ("Liver", "liver", [9, -1, 20], [3.0, 2.5, 2.8],
     "Hepatic tumors disrupt the low-shear sinusoidal architecture; the liver is also a major clearance organ.",
     ["hepatic_artery", "hepatic_vein", "portal_vein", "hepatic_arteriole"]),
    ("Kidney", "right_kidney", [10, -2, 15], [2.0, 1.8, 2.0],
     "Renal tumor vasculature is disorganised within a high-flow filtration organ.",
     ["r_renal_artery", "l_renal_artery", "renal_arteriole"]),
    ("Pancreas", "pancreas", [0, -4, 8], [2.5, 1.8, 2.2],
     "Dense desmoplastic stroma raises interstitial pressure and impairs convective transport.",
     ["splenic_artery", "mesenteric_arteriole"]),
    ("Breast", None, [6, -7, 28], [2.2, 1.6, 2.2],
     "Disorganised tumor microvasculature with low, oscillatory shear and elevated interstitial pressure.",
     ["r_subclavian_artery"]),
]


# ---------------------------------------------------------------------------
# Simulation-lab targets. These lived as three hard-coded coordinate triples inside
# docs/js/simlab.js — outside the single source of truth, and silently wrong the moment a vessel
# path moved. They are anchors on vessels now, like the hotspots.
# ---------------------------------------------------------------------------
_LAB_TARGETS = [
    ("carotid", "Carotid bifurcation", "r_common_carotid", 0.12, "low", "10–20 dyne/cm²", False),
    ("arch", "Aortic arch", "aortic_arch", 0.5, "moderate", "10–70 dyne/cm²", False),
    ("iliac", "Iliac bifurcation", "r_common_iliac", 0.05, "moderate", "10–70 dyne/cm²", False),
]


def build_lab_targets(vessels):
    return [
        {"id": tid, "label": label, "vesselId": vid, "tAlong": t,
         "pos": vessel_point(vessels, vid, t), "regime": regime,
         "wssText": wss_text, "disturbed": disturbed}
        for tid, label, vid, t, regime, wss_text, disturbed in _LAB_TARGETS
    ]


def build_tumor_sites():
    out = []
    for name, organ_id, pos, spread, note, near in _TUMOR_SITES:
        out.append({
            "id": slug(name), "label": name, "organ": organ_id,
            "pos": organ_center(organ_id, pos) if organ_id else list(map(float, pos)),
            "spread": list(map(float, spread)), "note": note,
            "nearVessels": list(near), "regime": "low_oscillatory",
            "representativeWss": 1.0, "schematic": True,
        })
    return out


# ---------------------------------------------------------------------------
# Nanoparticle journey — ordered waypoints. shearDyne in dyne/cm²; shear-RATE facts are copy only.
# integrityDelta values are authored/illustrative (schematic), not computed.
# ---------------------------------------------------------------------------
def build_journey():
    return {
        "carrier": "a ~100 nm liposome",
        "intro": "Follow a ~100 nm liposome from injection to its target — and watch what the "
                 "circulation's shear forces do to it along the way.",
        "waypoints": [
            {"id": "injection", "vesselId": "r_femoral_vein", "tAlong": 0.15,
             "title": "Injection — peripheral vein", "shearDyne": 3.0, "event": "Margination",
             "integrityDelta": -2,
             "copy": "In low-shear venous flow the carrier drifts toward the wall. Endothelial uptake "
                     "peaks at low shear (around 0.5 dyne/cm²), and residence time is long."},
            {"id": "heart", "vesselId": "pulmonary_trunk", "tAlong": 0.4,
             "title": "Through the right heart", "shearDyne": 20.0, "event": "Pulsatile loading",
             "integrityDelta": -3,
             "copy": "Entering the pulmonary circulation, pulsatile flow begins to flex the bilayer."},
            {"id": "aorta", "vesselId": "ascending_aorta", "tAlong": 0.5,
             "title": "Into the arterial tree", "shearDyne": 40.0,
             "shearRateNote": "venous→arterial shear rate (s⁻¹), giant-vesicle model",
             "event": "Permeability rises", "integrityDelta": -10,
             "copy": "Crossing from venous to arterial shear, model membranes leak more — up to +60% "
                     "permeability in giant-vesicle studies (a shear-rate effect)."},
            {"id": "carotid", "vesselId": "r_common_carotid", "tAlong": 0.5,
             "title": "Carotid bifurcation", "shearDyne": 15.0, "event": "Atheroprone niche",
             "integrityDelta": -3,
             "copy": "At the bifurcation, pockets of low and oscillatory shear (below ~4 dyne/cm²) mark "
                     "atheroprone endothelium — and a potential adhesion target."},
            {"id": "stenosis", "pos": [3.2, -0.5, 57], "title": "Stenotic hotspot",
             "shearDyne": 1000.0, "openEnded": True, "event": "Burst rupture", "integrityDelta": -70,
             "climax": True,
             "copy": "Shear above 1000 dyne/cm² can strip the carrier's hydration shell and rupture a "
                     "soft lipid bilayer — premature burst release, far from the target."},
            {"id": "sinusoid", "pos": [9.0, 0.0, 21.0], "title": "Target — hepatic sinusoid",
             "shearDyne": 0.3, "event": "Intended release zone", "integrityDelta": 0,
             "copy": "Near-stagnant sinusoidal shear (0.1–0.6 dyne/cm²) is where controlled release "
                     "should happen — if the carrier survived the trip."},
        ],
        "resolution": {
            "title": "Your carrier ruptured at the stenosis",
            "copy": "Most of the payload was released into the bloodstream at the shear hotspot, long "
                    "before reaching the target tissue. This is the biomechanical gap that benchtop "
                    "tests — run in near-still fluid — never reveal.",
        },
    }


# ---------------------------------------------------------------------------
# Quantitative panels
# ---------------------------------------------------------------------------
def build_panels():
    spectrum = [
        {"wss": 0.1, "label": "Hepatic sinusoids · lymphatics"},
        {"wss": 1.0, "label": "Veins"},
        {"wss": 10.0, "label": "Arteries (laminar)"},
        {"wss": 100.0, "label": "Severe stenosis onset"},
        {"wss": 1000.0, "label": "Stenotic hotspot"},
    ]
    shear_gap = [
        {"method": "Orbital shaking", "shear": SHEAR_GAP["orbital_shaking"], "kind": "benchtop"},
        {"method": "Magnetic stirring", "shear": SHEAR_GAP["magnetic_stirring"], "kind": "benchtop"},
        {"method": "Dialysis bag", "shear": SHEAR_GAP["dialysis_bag"], "kind": "benchtop"},
        {"method": "Microfluidic", "shear": SHEAR_GAP["microfluidic"], "kind": "benchtop"},
        {"method": "Physiological flow", "shear": SHEAR_GAP["physiological"], "openEnded": True,
         "kind": "physiological"},
    ]
    return {
        "spectrum": spectrum,
        "shearGap": shear_gap,
        "shearGapTakeaway": "Common release assays sit near 0.1–0.3 dyne/cm² — a thousand-fold below "
                            "the forces a carrier meets in flowing blood. A formulation can look stable "
                            "in a vial and still fail under physiological shear.",
        "regimes": {"low": REGIME_BINS["low"], "moderate": REGIME_BINS["moderate"]},
    }


# ---------------------------------------------------------------------------
# Assemble + serialise
# ---------------------------------------------------------------------------
def build_data():
    colorscale = [{"stop": round(_stop(c["wss"]), 6), "wss": c["wss"], "rgb": c["rgb"]}
                  for c in COLORSCALE]
    # Built once and threaded through: hotspots and lab targets are positions ON these paths.
    vessels = build_vessels()
    return {
        "meta": {
            "title": "The Hemodynamic Landscape",
            "wssUnit": "dyne/cm²", "logMin": LOG_MIN, "logMax": LOG_MAX,
            "note": "Representative WSS magnitudes consistent with the hemodynamics & nanomedicine "
                    "literature. Generated by build/build_data.py — do not edit by hand.",
        },
        "colorscale": colorscale,
        "groupColors": GROUP_COLORS,
        "vessels": vessels,
        "beds": build_beds(),
        "organs": build_organs(),
        "landmarks": build_landmarks(),
        "scenarios": build_scenarios(vessels),
        "tumorSites": build_tumor_sites(),
        "labTargets": build_lab_targets(vessels),
        "journey": build_journey(),
        "panels": build_panels(),
        "anatomy": {
            "source": ANATOMY.get("source"),
            "mmPerUnit": ANATOMY.get("transform", {}).get("mm_per_unit"),
            "anatomicalVessels": sum(1 for v in vessels if v["provenance"] == "anatomical"),
            "schematicVessels": sum(1 for v in vessels if v["provenance"] == "schematic"),
        } if ANATOMY else None,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    data = build_data()
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    json_path = os.path.join(OUT_DIR, "data.json")
    js_path = os.path.join(OUT_DIR, "data.js")
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(payload + "\n")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("// Generated by build/build_data.py — do not edit by hand.\n")
        f.write("export const DATA = " + payload + ";\n")
    n_v = len(data["vessels"])
    print(f"Wrote {json_path} and {js_path}")
    print(f"  vessels={n_v}  beds={len(data['beds'])}  organs={len(data['organs'])}  "
          f"scenarios={len(data['scenarios'])}  tumorSites={len(data['tumorSites'])}  "
          f"journey_waypoints={len(data['journey']['waypoints'])}")


if __name__ == "__main__":
    main()
