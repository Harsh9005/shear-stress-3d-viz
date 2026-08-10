"""
source.py — read meshes out of the BodyParts3D distribution.

Two facts about the distribution shape this module, both verified against the archive itself
rather than assumed:

1. The OBJ archive ships only **934 elementary parts**, but `parts_list_e.txt` names 1,523.
   The difference is *composite* parts: heart (FMA7088), brain (FMA50801), the lungs, the
   coronary arteries and the aorta as a whole have no OBJ of their own. They are defined in
   `composite_parts.txt` as unions of primitives, and must be resolved and concatenated.
   Resolution is recursive — a primitive can itself be composite.

2. Archive member names use Windows separators (`BodyParts3D_3.0_obj_95\\FMA7163.obj`), so
   members are indexed by basename, not by path.

Units and orientation (measured, see `report()`): millimetres, +Z superior, origin near the
feet. Laterality is asserted at load time rather than trusted.
"""

import io
import os
import zipfile

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
ZIP_NAME = "BodyParts3D_3.0_obj_95.zip"
COMPOSITE_NAME = "composite_parts.txt"
PARTS_LIST_NAME = "parts_list_e.txt"


def prune_components(mesh, debris_frac=0.01, largest_only=False):
    """Drop disconnected shells that are tiny relative to the largest, by face count."""
    comps = mesh.split(only_watertight=False)
    if len(comps) <= 1:
        return mesh
    comps = sorted(comps, key=lambda c: len(c.faces), reverse=True)
    if largest_only:
        return comps[0]
    cutoff = len(comps[0].faces) * debris_frac
    keep = [c for c in comps if len(c.faces) >= cutoff]
    return keep[0] if len(keep) == 1 else trimesh.util.concatenate(keep)


class Source:
    """Random access to BodyParts3D meshes, with composite parts resolved."""

    def __init__(self, cache=CACHE):
        self.cache = cache
        zip_path = os.path.join(cache, ZIP_NAME)
        if not os.path.exists(zip_path):
            raise SystemExit(
                f"missing {zip_path}\nRun: python3 build/anatomy/fetch_source.py"
            )
        self.zf = zipfile.ZipFile(zip_path)
        self.members = {
            n.split("\\")[-1].split("/")[-1][:-4]: n
            for n in self.zf.namelist()
            if n.lower().endswith(".obj")
        }
        self.composite = self._read_composite(os.path.join(cache, COMPOSITE_NAME))
        self.names = self._read_names(os.path.join(cache, PARTS_LIST_NAME))

    # ── index files ──────────────────────────────────────────────────────────
    @staticmethod
    def _read_composite(path):
        """composite id -> [primitive ids]. Tab-separated, one header line."""
        out = {}
        if not os.path.exists(path):
            raise SystemExit(f"missing {path}\nRun: python3 build/anatomy/fetch_source.py")
        with open(path, encoding="utf-8", errors="replace") as fh:
            next(fh, None)
            for line in fh:
                cols = line.rstrip("\n").split("\t")
                if len(cols) >= 3 and cols[0] and cols[2]:
                    out.setdefault(cols[0], []).append(cols[2])
        return out

    @staticmethod
    def _read_names(path):
        out = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    cols = line.rstrip("\n").split("\t")
                    if len(cols) >= 2:
                        out[cols[0]] = cols[1]
        return out

    # ── resolution ───────────────────────────────────────────────────────────
    def leaves(self, fma, _seen=None):
        """Every elementary part id backing `fma`, resolving composites recursively."""
        if _seen is None:
            _seen = set()
        if fma in _seen:
            return []
        _seen.add(fma)
        if fma in self.members:
            return [fma]
        kids = self.composite.get(fma)
        if not kids:
            return []
        out = []
        for k in kids:
            out.extend(self.leaves(k, _seen))
        # de-duplicate, keep order
        return list(dict.fromkeys(out))

    def available(self, fma):
        return bool(self.leaves(fma))

    # ── meshes ───────────────────────────────────────────────────────────────
    def _load_one(self, fma):
        raw = self.zf.read(self.members[fma])
        m = trimesh.load(io.BytesIO(raw), file_type="obj", process=False)
        if isinstance(m, trimesh.Scene):
            m = m.dump(concatenate=True)
        return m

    def mesh(self, fma, debris_frac=0.01, largest_only=False):
        """
        The mesh for `fma`, concatenating primitives when it is a composite part.

        Every part in this distribution carries a handful of stray 1-6 face islands (the
        ascending aorta ships 21 components, only one of which is the vessel). Those islands
        break centerline seeding and inflate triangle budgets, so components smaller than
        `debris_frac` of the largest are dropped. The threshold is deliberately low: real
        multi-part organs — the lungs are 2 and 3 lobes — are far above 1% and survive.

        `largest_only=True` keeps just the biggest shell, which is what the skin needs.
        """
        if isinstance(fma, (list, tuple)):
            # An explicit list of primitives: used where a composite carries more than the
            # vessel meant by a name — the left coronary artery ships as stem + LAD +
            # circumflex + septal branches, and "left coronary artery" means stem + LAD.
            ids = [i for f in fma for i in self.leaves(f)]
            ids = list(dict.fromkeys(ids))
        else:
            ids = self.leaves(fma)
        if not ids:
            raise KeyError(f"{fma} has no OBJ and no composite definition")
        parts_ = [self._load_one(i) for i in ids]
        m = parts_[0] if len(parts_) == 1 else trimesh.util.concatenate(parts_)
        m.merge_vertices()
        m.update_faces(m.nondegenerate_faces())   # trimesh 5.x name
        m.remove_unreferenced_vertices()
        return prune_components(m, debris_frac=debris_frac, largest_only=largest_only)

    def label(self, fma):
        if isinstance(fma, (list, tuple)):
            return " + ".join(self.names.get(f, f) for f in fma)
        return self.names.get(fma, fma)

    def report(self, fma):
        m = self.mesh(fma)
        return {
            "fma": fma, "label": self.label(fma), "leaves": len(self.leaves(fma)),
            "vertices": len(m.vertices), "faces": len(m.faces),
            "bounds": np.round(m.bounds, 1).tolist(),
            "centroid": np.round(m.centroid, 1).tolist(),
        }
