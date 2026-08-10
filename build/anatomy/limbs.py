"""
limbs.py — derive limb centre-axes from the real body surface.

BodyParts3D segments no limb arteries at all (verified in parts.py), so the app's brachial and
femoral vessels cannot be extracted from it. They stay hand-authored — but "hand-authored" does
not have to mean "floating next to the body", which is what the old scene did. This module
reads the real skin surface and works out where each limb actually is, so a schematic vessel can
be laid down the middle of a real arm or leg.

Method: slice the body into horizontal slabs and, within each slab, cluster vertices along X.
An upper-arm slab yields three clusters — right arm, torso, left arm — and the arm is simply the
outermost one on the requested side. A thigh slab yields two, one per leg. Gaps between clusters
are found rather than assumed, so nothing here depends on a hard-coded body width.

Everything is in scene units, in the app's frame (+X is the subject's right, -Y anterior,
+Z superior), because it runs on the already-transformed body mesh.
"""

import numpy as np


def _clusters_1d(values, gap):
    """Split sorted values wherever consecutive ones are more than `gap` apart."""
    if len(values) == 0:
        return []
    order = np.sort(values)
    breaks = np.where(np.diff(order) > gap)[0]
    groups, start = [], 0
    for b in breaks:
        groups.append(order[start:b + 1])
        start = b + 1
    groups.append(order[start:])
    return groups


def limb_axis(body_vertices, side, z_from, z_to, start="lateral",
              slabs=14, gap=2.0, band=7.0, min_points=25):
    """
    Centre-axis of one limb between two heights, proximal -> distal.

    side:  "right" or "left" (subject's, i.e. +X is right in the app frame)
    start: which cluster to lock onto in the first slab — "lateral" for an arm, "medial" for a
           leg. Both are needed because arms and legs overlap in height: a standing figure's
           fingertips reach mid-thigh, so a thigh slab contains a hand as well as a leg, and
           "take the outermost cluster" would walk a femoral vessel down the arm.

    After the first slab the limb is followed by continuity — each slab takes the cluster whose
    centre is nearest the previous slab's — so the trace stays on one limb through the elbow and
    knee rather than jumping to whatever is furthest out at that height.

    Returns an (n,3) polyline, or None where the limb could not be resolved.
    """
    v = np.asarray(body_vertices, dtype=float)
    sign = 1.0 if side == "right" else -1.0
    zs = np.linspace(z_from, z_to, slabs + 1)
    pts, last_x = [], None
    for i in range(slabs):
        lo, hi = min(zs[i], zs[i + 1]), max(zs[i], zs[i + 1])
        sl = v[(v[:, 2] >= lo) & (v[:, 2] < hi)]
        if len(sl) < min_points:
            continue
        sl = sl[sl[:, 0] * sign > 0]
        if len(sl) < min_points:
            continue
        if start == "band":
            # Outermost slice of the limb rather than a cluster. With the arms hanging against
            # the trunk this model has no gap between arm and torso at most heights, so there is
            # nothing to cluster on; the arm is still reliably the outermost tissue at that
            # height, and `band` is roughly one limb width.
            edge = float(sl[:, 0].max()) if sign > 0 else float(sl[:, 0].min())
            sel = sl[np.abs(sl[:, 0] - edge) <= band]
        else:
            groups = [g for g in _clusters_1d(sl[:, 0], gap) if len(g) >= 6]
            if not groups:
                continue
            if last_x is None:
                key = (lambda g: abs(np.mean(g))) if start == "lateral" else (lambda g: -abs(np.mean(g)))
                target = max(groups, key=key)
            else:
                target = min(groups, key=lambda g: abs(np.mean(g) - last_x))
            xlo, xhi = float(target.min()), float(target.max())
            sel = sl[(sl[:, 0] >= xlo - 1e-6) & (sl[:, 0] <= xhi + 1e-6)]
        if len(sel) < 6:
            continue
        last_x = float(sel[:, 0].mean())
        pts.append([last_x, sel[:, 1].mean(), (lo + hi) / 2.0])
    if len(pts) < 3:
        return None
    return np.array(pts)


def offset_axis(axis, anterior=0.0, medial=0.0, side="right"):
    """
    Shift a limb axis off-centre.

    Limb vessels do not run down the geometric middle of a limb: the brachial artery lies
    medial and anterior in the upper arm, the femoral vessels anteromedial in the thigh. The
    offsets are small and are what keeps a schematic vessel from reading as a rod through the
    bone.  -Y is anterior; medial means toward the midline, so it opposes the side's sign.
    """
    out = np.array(axis, dtype=float)
    sign = 1.0 if side == "right" else -1.0
    out[:, 1] -= anterior
    out[:, 0] -= medial * sign
    return out


def resample(points, n):
    """Even arc-length resampling (duplicated from centerline.py's helper for independence)."""
    p = np.asarray(points, dtype=float)
    if len(p) < 2:
        return p
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] <= 0:
        return p[:1].repeat(n, axis=0)
    t = np.linspace(0.0, s[-1], n)
    return np.column_stack([np.interp(t, s, p[:, k]) for k in range(3)])


def smooth(points, passes=2):
    p = np.array(points, dtype=float)
    for _ in range(passes):
        if len(p) < 3:
            break
        q = p.copy()
        q[1:-1] = 0.25 * p[:-2] + 0.5 * p[1:-1] + 0.25 * p[2:]
        p = q
    return p


# Where each limb vessel runs, in scene units. z_from/z_to are read off the fitted body, and the
# offsets place the vessel on the correct aspect of the limb. Anything listed here is schematic
# by construction — the source has no limb vasculature — and is labelled as such in the data.
LIMB_VESSELS = {
    # shoulder to elbow: the brachial artery ends at the elbow, and below it the hand
    # sits close enough to the thigh that the two merge into one cluster
    "r_brachial_artery": dict(side="right", start="band", z_from=40, z_to=14, anterior=0.8, medial=3.6),
    "l_brachial_artery": dict(side="left",  start="band", z_from=40, z_to=14, anterior=0.8, medial=3.6),
    "r_femoral_artery":  dict(side="right", start="medial", z_from=-18, z_to=-62, anterior=1.6, medial=1.0),
    "l_femoral_artery":  dict(side="left",  start="medial", z_from=-18, z_to=-62, anterior=1.6, medial=1.0),
    "r_femoral_vein":    dict(side="right", start="medial", z_from=-18, z_to=-62, anterior=1.0, medial=2.0),
    "l_femoral_vein":    dict(side="left",  start="medial", z_from=-18, z_to=-62, anterior=1.0, medial=2.0),
}


def build_limb_paths(body_vertices, n_points=8):
    """
    Every limb vessel path the app needs, keyed by app vessel id.

    Arms are traced from the elbow upward and then reversed. At the shoulder the arm and the
    torso are one continuous surface with no gap between them, so a trace started there locks
    onto the merged cluster and drifts to the midline; at the elbow the arm is unambiguously
    separate, and continuity carries the trace back up through the shoulder correctly.
    """
    out = {}
    for vid, spec in LIMB_VESSELS.items():
        z_from, z_to = spec["z_from"], spec["z_to"]
        flip = bool(spec.get("trace_from_distal"))
        if flip:
            z_from, z_to = z_to, z_from
        axis = limb_axis(body_vertices, spec["side"], z_from, z_to,
                         start=spec.get("start", "lateral"), band=spec.get("band", 7.0))
        if axis is None:
            continue
        if flip:
            axis = axis[::-1]
        axis = offset_axis(axis, spec["anterior"], spec["medial"], spec["side"])
        out[vid] = resample(smooth(axis, passes=2), n_points)
    return out
