#!/usr/bin/env python3
"""
fit_transform.py — fit the similarity transform that carries BodyParts3D coordinates into the
app's existing scene frame, and write it to build/anatomy/transform.json.

Why a fit rather than a hand-picked scale
-----------------------------------------
The app's scene frame was drawn by hand and never had a stated unit. Fitting it against real
anatomy is what tells us what the frame actually is, instead of guessing. The answer (see the
generated transform.json) is ~5.8 mm per scene unit, with the origin near the aortic
bifurcation — a frame that is internally coherent: it puts the bifurcation at ~98 cm above the
floor, the carotid ends at the jaw, and the femoral ends at the knee.

Handedness
----------
BodyParts3D uses -X for the subject's RIGHT (verified: right lung centroid x=-66, left lung
x=+70, right kidney x=-67, liver x=-45). The app uses +X for the subject's right (its
"R. Subclavian Artery" runs to x=+15). So the transform includes a mirror in X. Mirroring the
whole dataset consistently keeps the anatomy correct in the app's convention — the liver still
sits on the subject's right — it is simply the mirror image of this particular cadaver, which
is anatomically immaterial.

Landmarks
---------
The aorta is the structure the app drew most carefully and the spine of the visualization, so
the correspondences are drawn from it and its first-order branches. Residuals are reported:
they are the app's hand-drawing error, and they are the reason the vessel paths are re-derived
from the anatomy rather than nudged.

Run:  python3 build/anatomy/fit_transform.py
"""

import json
import os

import numpy as np

from source import Source

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "transform.json")

# BodyParts3D -X is the subject's right; the app uses +X. See module docstring.
MIRROR = np.array([-1.0, 1.0, 1.0])

# (label, app point, source part, axis, sign) — the source point is the extreme vertex of that
# part along `axis` (sign +1 = maximum, -1 = minimum), taken after mirroring.
LANDMARKS = [
    ("ascending aorta root",  (1.0, -5.0, 35.0),   "FMA3736",  2, -1),
    ("aortic arch apex",      (-1.0, 1.0, 49.0),   "FMA3768",  2, +1),
    ("aortic bifurcation",    (0.0, -5.0, -8.0),   "FMA3784",  2, -1),
    ("R. carotid distal",     (2.5, 0.0, 70.0),    "FMA3941",  2, +1),
    ("L. carotid distal",     (-2.5, 0.0, 70.0),   "FMA4058",  2, +1),
    ("R. iliac distal",       (6.0, -4.0, -16.0),  "FMA14765", 2, -1),
    ("L. iliac distal",       (-6.0, -4.0, -16.0), "FMA14766", 2, -1),
]


def extreme_point(src, fma, axis, sign):
    v = src.mesh(fma).vertices * MIRROR
    return v[np.argmax(sign * v[:, axis])]


def fit(src):
    """Least-squares uniform scale + translation (no rotation; the axes already correspond)."""
    app = np.array([p for _, p, _, _, _ in LANDMARKS], dtype=float)
    raw = np.array([extreme_point(src, f, a, s) for _, _, f, a, s in LANDMARKS], dtype=float)
    rc, ac = raw - raw.mean(0), app - app.mean(0)
    scale = float((rc * ac).sum() / (rc * rc).sum())
    translate = app.mean(0) - scale * raw.mean(0)
    predicted = scale * raw + translate
    residual = predicted - app
    return {
        "mirror": MIRROR.tolist(),
        "scale": scale,
        "translate": translate.tolist(),
        "mm_per_unit": 1.0 / scale,
        "rms_residual_units": float(np.sqrt((residual ** 2).sum(1).mean())),
        "landmarks": [
            {"label": lab, "app": list(a), "fitted": [round(x, 2) for x in p],
             "residual": [round(x, 2) for x in r]}
            for (lab, a, _, _, _), p, r in zip(LANDMARKS, predicted, residual)
        ],
        "source": "BodyParts3D 3.0 (CC BY-SA 2.1 Japan)",
    }


def apply(points, tf):
    """Map BodyParts3D coordinates into the app frame."""
    p = np.asarray(points, dtype=float)
    return p * np.asarray(tf["mirror"]) * tf["scale"] + np.asarray(tf["translate"])


def load(path=OUT):
    if not os.path.exists(path):
        raise SystemExit(f"missing {path}\nRun: python3 build/anatomy/fit_transform.py")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    src = Source()
    tf = fit(src)
    print(f"scale     {tf['scale']:.6f}   ({tf['mm_per_unit']:.2f} mm per scene unit)")
    print(f"translate {[round(x, 3) for x in tf['translate']]}")
    print(f"mirror    {tf['mirror']}")
    print(f"RMS residual {tf['rms_residual_units']:.2f} scene units "
          f"({tf['rms_residual_units'] * tf['mm_per_unit'] / 10:.1f} cm)")
    for lm in tf["landmarks"]:
        print(f"   {lm['label']:<22} app={lm['app']}  fitted={lm['fitted']}  resid={lm['residual']}")

    body = apply(src.mesh("FMA7163", largest_only=True).vertices, tf)
    lo, hi = body.min(0), body.max(0)
    tf["body_bounds"] = [lo.tolist(), hi.tolist()]
    print(f"\nbody in app frame: {np.round(lo, 1).tolist()} .. {np.round(hi, 1).tolist()}"
          f"   height {float(hi[2] - lo[2]):.1f} units "
          f"({float(hi[2] - lo[2]) * tf['mm_per_unit'] / 10:.0f} cm)")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(tf, fh, indent=2)
        fh.write("\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
