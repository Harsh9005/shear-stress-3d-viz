#!/usr/bin/env python3
"""
build_anatomy.py — turn the BodyParts3D source into the web assets the app ships.

Outputs (all committed; the 547 MB source archive is not):
    docs/assets/anatomy/body.glb     outer skin surface — the realistic silhouette
    docs/assets/anatomy/organs.glb   named organ nodes (brain, lungs, liver, kidneys, ...)
    docs/assets/anatomy/heart.glb    the heart
    build/anatomy/vessels.json       centerlines for the vessels this source actually contains

Everything is emitted already transformed into the app's scene frame (see fit_transform.py), so
the browser does no coordinate maths and the fit is reviewable as committed data.

Triangle budgets exist because this is a GitHub Pages site with a hard payload budget, not
because the source lacks detail: the skin arrives as 1.6 M faces across 31,130 shells, of which
exactly one is the body.

Run:  python3 build/anatomy/build_anatomy.py
"""

import argparse
import json
import os
import time

import numpy as np
import trimesh

import parts
from centerline import (longest_path, path_to_extreme, resample, seed_vertex, smooth,
                        trace, trace_axis, trace_single)
from limbs import build_limb_paths
from fit_transform import apply as apply_transform
from fit_transform import load as load_transform
from source import Source, prune_components

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
ASSET_DIR = os.path.join(REPO, "docs", "assets", "anatomy")
VESSELS_OUT = os.path.join(HERE, "vessels.json")

# Face budgets. The body carries the silhouette so it gets the most; organs read as soft
# volumes behind a translucent skin and hold up at a few thousand each.
#
# 32,000 was tried and raised: at that budget the shipped skin deviates from the true surface by
# ~20 mm at the 95th percentile, which is larger than the clearance between a vessel and the
# skin, so containment could not be judged against it at all. 72,000 halves that error and still
# leaves the whole asset set inside the payload budget.
BUDGET_BODY = 72000
BUDGET_HEART = 12000
BUDGET_ORGAN = 4500

CENTERLINE_BINS = 40
CENTERLINE_POINTS = 12          # resampled; the app rebuilds a Catmull-Rom curve from these


def decimate(mesh, target_faces):
    """Quadric decimation down to `target_faces`, a no-op if the mesh is already smaller."""
    if len(mesh.faces) <= target_faces:
        return mesh
    return mesh.simplify_quadric_decimation(face_count=target_faces)


def to_app_frame(mesh, tf):
    out = mesh.copy()
    out.vertices = apply_transform(out.vertices, tf)
    # A mirror flips winding order; fix it so normals still point outward.
    if np.prod(tf["mirror"]) < 0:
        out.invert()
    return out


def export(scene_or_mesh, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = scene_or_mesh.export(file_type="glb")
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


def build_body(src, tf):
    t0 = time.time()
    m = src.mesh(list(parts.BODY)[0], largest_only=True)
    raw = len(m.faces)
    m = decimate(m, BUDGET_BODY)
    m = to_app_frame(m, tf)
    size = export(m, os.path.join(ASSET_DIR, "body.glb"))
    print(f"  body.glb    {raw:>9,} -> {len(m.faces):>6,} faces  {size/1024:7.0f} KB  "
          f"({time.time()-t0:.0f}s)")
    return m


def build_heart(src, tf):
    m = src.mesh(list(parts.HEART)[0])
    raw = len(m.faces)
    m = to_app_frame(decimate(m, BUDGET_HEART), tf)
    size = export(m, os.path.join(ASSET_DIR, "heart.glb"))
    print(f"  heart.glb   {raw:>9,} -> {len(m.faces):>6,} faces  {size/1024:7.0f} KB")
    return m


def build_organs(src, tf):
    """One GLB holding every organ as a named node, so the app can pick and label them."""
    scene = trimesh.Scene()
    centroids = {}
    for key, (fma, label) in parts.ORGANS.items():
        m = src.mesh(fma)
        raw = len(m.faces)
        m = to_app_frame(decimate(m, BUDGET_ORGAN), tf)
        scene.add_geometry(m, node_name=key, geom_name=key)
        centroids[key] = {"label": label, "fma": fma,
                          "centroid": [round(float(x), 2) for x in m.centroid],
                          "extents": [round(float(x), 2) for x in m.extents]}
        print(f"    {key:<14} {raw:>8,} -> {len(m.faces):>6,} faces")
    size = export(scene, os.path.join(ASSET_DIR, "organs.glb"))
    print(f"  organs.glb  {len(parts.ORGANS)} organs               {size/1024:7.0f} KB")
    return centroids


def side_submesh(mesh, side, span_mm):
    """
    The part of a mesh lying on one side of the midline, out to `span_mm`.

    This is how one mesh holding several vessels yields a single named one. The pulmonary
    artery arrives as trunk + both branches + everything that ramifies inside both lungs, and
    the pulmonary veins arrive as four mutually disconnected veins. Masking vertices alone is
    not enough — the trace seed then sits in a different shell from the vertices it is supposed
    to reach — so the mask is turned into a real submesh and re-seeded inside it.

    Source coordinates are un-mirrored, so the subject's RIGHT is -X. `span_mm` stops the
    course at the hilum rather than following branches into the lung.
    """
    x = mesh.vertices[:, 0]
    mid = float(np.median(x))
    keep = (x <= mid) & (x >= mid - span_mm) if side == "right" else \
           (x >= mid) & (x <= mid + span_mm)
    faces = keep[mesh.faces].all(axis=1)
    if faces.sum() < 8:
        raise ValueError(f"side mask '{side}' keeps too little of the mesh")
    sub = mesh.submesh([np.where(faces)[0]], append=True)
    sub = prune_components(sub, largest_only=True)
    # Re-seed at the medial end — the vessel's origin, nearest the midline.
    sx = sub.vertices[:, 0]
    seed = int(np.argmax(sx)) if side == "right" else int(np.argmin(sx))
    return sub, seed


def _branch_pick(mesh, seed, which):
    """
    Pull one named course out of a branching vessel mesh.

    "trunk"   the segment before the first real fork
    "right"   / "left"  the root-to-leaf path reaching furthest into that hemithorax
    "longest" the longest root-to-leaf path — used where a vessel's stem is very short and the
              interesting course is the stem plus its main continuation (the left coronary's
              stem is under a centimetre; the vessel people mean is stem + LAD)

    Source coordinates are still un-mirrored here, so the subject's RIGHT is -X.
    """
    segs = trace(mesh, seed=seed, bins=CENTERLINE_BINS)
    if which == "longest":
        return longest_path(segs)
    if which == "right":
        return path_to_extreme(segs, axis=0, sign=-1)
    if which == "left":
        return path_to_extreme(segs, axis=0, sign=+1)
    trunk = segs[0]["points"]
    # A trunk that traced to almost nothing means the fork is immediate; the useful course is
    # then the longest path, not a two-point stub.
    if len(trunk) < 3:
        return longest_path(segs)
    return trunk


def build_vessels(src, tf):
    """Extract a centerline per app vessel that this source actually contains."""
    out = {}
    for vid, spec in parts.VESSEL_SOURCES.items():
        try:
            m = src.mesh(spec["fma"])
            side = spec.get("side")
            if side:
                m, seed = side_submesh(m, side, spec.get("side_span_mm", 75))
            else:
                seed = seed_vertex(m, spec["seed_axis"], spec["seed_sign"])
            if spec["mode"] == "axis":
                pts = trace_axis(m, axis=spec.get("axis", 0), sign=spec.get("axis_sign", +1),
                                 bins=spec.get("axis_bins", 20))
            elif spec["mode"] == "single":
                pts = trace_single(m, seed=seed, bins=CENTERLINE_BINS,
                                   max_dist=spec.get("max_len_mm"))
            else:
                pts = _branch_pick(m, seed, spec.get("pick", "trunk"))
                if len(pts) < 2:
                    raise ValueError("branch pick produced no polyline")
            pts = resample(smooth(pts, passes=spec.get("smooth_passes", 2)), CENTERLINE_POINTS)
            pts = apply_transform(pts, tf)
            length_mm = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()) * tf["mm_per_unit"]
            out[vid] = {
                "fma": spec["fma"] if isinstance(spec["fma"], str) else list(spec["fma"]),
                "sourceName": src.label(spec["fma"]),
                "path": [[round(float(c), 3) for c in p] for p in pts],
                "lengthMm": round(length_mm, 1),
            }
            tag = spec["fma"] if isinstance(spec["fma"], str) else "+".join(spec["fma"])
            print(f"    {vid:<22} {tag:<20} {len(m.faces):>7,} faces  {length_mm:6.0f} mm")
        except Exception as exc:                       # one bad part must not kill the build
            tag = spec["fma"] if isinstance(spec["fma"], str) else "+".join(spec["fma"])
            print(f"    {vid:<22} {tag:<20} FAILED: {exc}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-meshes", action="store_true", help="rebuild vessels.json only")
    args = ap.parse_args()

    src = Source()
    tf = load_transform()
    print(f"transform: {tf['mm_per_unit']:.2f} mm/unit, mirror={tf['mirror']}")

    centroids, body_bounds, limb_paths, heart_info = {}, None, {}, None
    if not args.skip_meshes:
        print("meshes:")
        body = build_body(src, tf)
        body_bounds = [body.bounds[0].tolist(), body.bounds[1].tolist()]
        heart = build_heart(src, tf)
        heart_info = {"center": [round(float(x), 2) for x in heart.centroid],
                      "extents": [round(float(x), 2) for x in heart.extents]}
        centroids = build_organs(src, tf)

        print("limbs (schematic vessels seated in the real body):")
        for vid, path in build_limb_paths(body.vertices).items():
            limb_paths[vid] = [[round(float(c), 3) for c in p] for p in path]
            span = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
            print(f"    {vid:<22} {len(path)} pts  {span * tf['mm_per_unit'] / 10:5.0f} cm")

    print("vessels:")
    vessels = build_vessels(src, tf)

    payload = {
        "source": parts.ATTRIBUTION,
        "transform": {k: tf[k] for k in ("mirror", "scale", "translate", "mm_per_unit")},
        "vessels": vessels,
        "limbPaths": limb_paths,
        "schematicVessels": parts.SCHEMATIC_VESSELS,
    }
    if centroids:
        payload["organs"] = centroids
        payload["bodyBounds"] = body_bounds
        payload["heart"] = heart_info
    elif os.path.exists(VESSELS_OUT):
        # --skip-meshes must not drop what only the mesh pass can produce.
        with open(VESSELS_OUT, encoding="utf-8") as fh:
            prev = json.load(fh)
        for k in ("organs", "bodyBounds", "heart", "limbPaths"):
            if prev.get(k):
                payload[k] = prev[k]

    with open(VESSELS_OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    print(f"\nwrote {VESSELS_OUT}: {len(vessels)} anatomical, "
          f"{len(parts.SCHEMATIC_VESSELS)} schematic")

    if os.path.isdir(ASSET_DIR):
        total = sum(os.path.getsize(os.path.join(ASSET_DIR, f))
                    for f in os.listdir(ASSET_DIR) if f.endswith(".glb"))
        print(f"asset payload: {total/1024:.0f} KB")


if __name__ == "__main__":
    main()
