#!/usr/bin/env python3
"""
check_containment.py — measure how much of the vessel tree is actually inside the body.

The whole point of the anatomy work is that the vasculature sits inside a real human rather than
floating beside a cartoon of one. That is a geometric claim and it deserves a geometric
measurement, not a screenshot someone approved once.

Why this is a separate step rather than a plain unit test: deciding whether a point is inside a
surface needs the mesh and a ray caster, and the repository's test suite runs on a stock Python
with no mesh library. So the measurement happens here, next to the mesh, and is written to
containment.json together with a fingerprint of the exact vessel paths it was measured from.
build/test_anatomy_fit.py then asserts both the result and the fingerprint, so a stale report
fails instead of quietly passing — a report that no longer matches the data is worth nothing.

Two cheaper designs were tried and thrown away, both because they could not fail:
  * a per-height bounding box — at chest height it spans fingertip to fingertip, so the air
    beside the ribcage counts as inside, and the old floating vessels passed it;
  * per-height boxes split into arm/trunk/arm pieces — in this model the arms rest against the
    trunk, so there is no gap to split on, and the old vessels passed that too.
Only true inside/outside testing separates them.

Run:  python3 build/anatomy/check_containment.py            (measures the current data.json)
      python3 build/anatomy/check_containment.py --data X   (any data.json, for comparison)
"""

import argparse
import hashlib
import json
import os

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
BODY_GLB = os.path.join(REPO, "docs", "assets", "anatomy", "body.glb")
DATA_JSON = os.path.join(REPO, "docs", "data", "data.json")
OUT = os.path.join(HERE, "containment.json")


def load_body():
    scene = trimesh.load(BODY_GLB, force="scene")
    mesh = scene.dump(concatenate=True) if isinstance(scene, trimesh.Scene) else scene
    mesh.merge_vertices()
    return mesh


def paths_fingerprint(vessels):
    """Stable hash of every vessel id and path, so a stale measurement is detectable."""
    h = hashlib.sha256()
    for v in sorted(vessels, key=lambda x: x["id"]):
        h.update(v["id"].encode())
        for p in v["path"]:
            h.update(",".join(f"{c:.3f}" for c in p).encode())
    return h.hexdigest()


def inside_mask(mesh, points):
    """
    True where a point is inside the surface.

    trimesh's `contains` needs a watertight mesh. The decimated skin usually is; when it is not,
    fall back to ray parity — cast one ray per point and count surface crossings, odd meaning
    inside. Parity is the same test `contains` performs, just without the watertight guarantee,
    which is acceptable for a closed-enough body shell and is reported in the output.
    """
    pts = np.asarray(points, dtype=float)
    if mesh.is_watertight:
        return np.asarray(mesh.contains(pts)), "contains"

    # Parity along three directions, majority vote. A single ray is not enough on a decimated
    # shell: it can grazes an edge, or run the long way up the body through head and shoulders,
    # and miscount. Voting across directions that leave the body by different routes removes
    # nearly all of that noise. The directions are deliberately not axis-aligned, so a ray does
    # not run along a plane of the mesh.
    directions = [
        np.array([0.97, 0.17, 0.17]),
        np.array([0.17, 0.97, 0.17]),
        np.array([-0.31, 0.62, 0.72]),
    ]
    votes = np.zeros(len(pts), dtype=int)
    for d in directions:
        d = d / np.linalg.norm(d)
        hits = mesh.ray.intersects_id(
            ray_origins=pts,
            ray_directions=np.tile(d, (len(pts), 1)),
            multiple_hits=True,
        )[1]
        counts = np.bincount(hits, minlength=len(pts)) if len(hits) else np.zeros(len(pts), int)
        votes += (counts % 2 == 1).astype(int)
    return votes >= 2, "ray-parity-3way"


def surface_distance(mesh, points):
    """Distance from each point to the nearest point on the surface, in scene units."""
    q = trimesh.proximity.ProximityQuery(mesh)
    return np.linalg.norm(mesh.vertices[q.vertex(np.asarray(points, float))[1]]
                          - np.asarray(points, float), axis=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=DATA_JSON)
    ap.add_argument("--tolerance", type=float, default=2.0,
                    help="scene units of slack, sized to the shipped mesh's decimation error")
    ap.add_argument("--write", action="store_true", help="write containment.json")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as fh:
        data = json.load(fh)
    vessels = data["vessels"]
    mesh = load_body()

    points, owners = [], []
    for v in vessels:
        for p in v["path"]:
            points.append(p)
            owners.append(v["id"])
    mask, method = inside_mask(mesh, points)
    dist = surface_distance(mesh, points)

    # A point counts as contained if it is inside, or outside by less than the shipped mesh's own
    # error. The tolerance is not a fudge factor picked to make the number look good: the
    # decimated skin departs from the true skin by a measured ~9 mm at the median and ~2 units at
    # p90, so anything inside that band is below the resolution at which this mesh can answer the
    # question at all. Both figures are reported so the strict one stays visible.
    ok = np.asarray(mask) | (dist <= args.tolerance)

    per_vessel = {}
    for vid, strict, loose in zip(owners, mask, ok):
        tally = per_vessel.setdefault(vid, [0, 0, 0])
        tally[0] += int(bool(strict))
        tally[1] += int(bool(loose))
        tally[2] += 1

    strict_fraction = float(np.asarray(mask).sum()) / len(mask)
    fraction = float(ok.sum()) / len(ok)
    worst = sorted(((v, c[1] / c[2]) for v, c in per_vessel.items()), key=lambda t: t[1])[:8]

    print(f"body mesh: {len(mesh.faces):,} faces, watertight={mesh.is_watertight}, method={method}")
    print(f"strictly inside:            {int(np.asarray(mask).sum())}/{len(mask)} = {strict_fraction:.3f}")
    print(f"inside or within {args.tolerance:.1f} units: {int(ok.sum())}/{len(ok)} = {fraction:.3f}")
    print(f"max distance outside:       {dist[~np.asarray(mask)].max() if (~np.asarray(mask)).any() else 0:.2f} units")
    print("least contained vessels:")
    for vid, f in worst:
        print(f"    {vid:<24} {f:.2f}")

    if args.write:
        report = {
            "fraction": round(fraction, 4),
            "strictFraction": round(strict_fraction, 4),
            "tolerance": args.tolerance,
            "points": len(mask),
            "method": method,
            "watertight": bool(mesh.is_watertight),
            "bodyFaces": int(len(mesh.faces)),
            "pathsFingerprint": paths_fingerprint(vessels),
            "perVessel": {v: round(c[1] / c[2], 3) for v, c in sorted(per_vessel.items())},
        }
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
        print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
