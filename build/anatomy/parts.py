"""
parts.py — the curated FMA-ID -> role map for the anatomy asset pipeline.

Source: BodyParts3D 3.0 (Database Center for Life Science, Japan), CC BY-SA 2.1 Japan.
Every ID below was looked up in the distribution's own `parts_list_e.txt`; none is guessed.

Roles
-----
BODY     the outer skin surface — the realistic silhouette that replaces the old ellipsoid blobs
HEART    the heart, replacing the old sphere
ORGANS   named organs the app already references (tooltips, tumor sites, sinusoidal beds)
ARTERIES / VEINS
         real trunk vasculature. NOTE the coverage limit recorded below.

Coverage limit (verified against parts_list_e.txt, not assumed)
--------------------------------------------------------------
BodyParts3D's vascular segmentation is TRUNK-ONLY. It contains the aorta and its major
branches, the coronary tree, the caval/portal veins and the iliacs — but it contains NO limb
arteries (no brachial, femoral, popliteal, radial, tibial) and NO cerebral arteries (no circle
of Willis, no basilar, no vertebral). Names matching those words in the distribution are
muscles and brain tissue, not vessels.

Consequence: vessels derived from this source are real anatomy; the limb and cerebral vessels
the app also shows cannot be, and stay hand-authored and flagged schematic. The app already has
a `schematic: true` convention (tumor sites) and that is the honest label to reuse.
"""

# ── The outer body surface ────────────────────────────────────────────────────
# The distribution's skin part mixes outer and inner surfaces; build_anatomy.py keeps only the
# largest outward-facing shell. Do not use this mesh raw.
BODY = {"FMA7163": "skin"}

HEART = {"FMA7088": "heart"}

# ── Organs the app names ──────────────────────────────────────────────────────
# Keys are the app-side organ ids used in data.json / tumor sites; values are (FMA id, label).
ORGANS = {
    "brain":       ("FMA50801", "Brain"),
    "right_lung":  ("FMA7309", "R. Lung"),
    "left_lung":   ("FMA7310", "L. Lung"),
    "liver":       ("FMA7197", "Liver"),
    "spleen":      ("FMA7196", "Spleen"),
    "pancreas":    ("FMA7198", "Pancreas"),
    "right_kidney": ("FMA7204", "R. Kidney"),
    "left_kidney":  ("FMA7205", "L. Kidney"),
}

# ── Real trunk vasculature ────────────────────────────────────────────────────
# Used in Phase 0 to fit the coordinate transform, and in Phase 2 to derive centerlines.
ARTERIES = {
    "aorta":                  "FMA3734",
    "ascending_aorta":        "FMA3736",
    "arch_of_aorta":          "FMA3768",
    "descending_aorta":       "FMA3784",
    "thoracic_aorta":         "FMA3786",
    "brachiocephalic_artery": "FMA3932",
    "r_common_carotid":       "FMA3941",
    "l_common_carotid":       "FMA4058",
    "r_subclavian":           "FMA3953",
    "l_subclavian":           "FMA4694",
    "r_coronary":             "FMA50039",
    "l_coronary":             "FMA50040",
    "celiac":                 "FMA50737",
    "common_hepatic":         "FMA14771",
    "splenic_artery":         "FMA14773",
    "superior_mesenteric":    "FMA14749",
    "inferior_mesenteric":    "FMA14750",
    "r_renal_artery":         "FMA14752",
    "l_renal_artery":         "FMA14753",
    "r_common_iliac":         "FMA14765",
    "l_common_iliac":         "FMA14766",
    "r_external_iliac":       "FMA18806",
    "l_external_iliac":       "FMA18807",
    "pulmonary_artery":       "FMA66326",
}

VEINS = {
    "superior_vena_cava":  "FMA4720",
    "inferior_vena_cava":  "FMA10951",
    "r_brachiocephalic":   "FMA4751",
    "l_brachiocephalic":   "FMA4761",
    "r_internal_jugular":  "FMA4754",
    "l_internal_jugular":  "FMA4762",
    "r_subclavian_vein":   "FMA4755",
    "l_subclavian_vein":   "FMA4763",
    "r_renal_vein":        "FMA14335",
    "l_renal_vein":        "FMA14336",
    "splenic_vein":        "FMA14331",
    "superior_mesenteric_vein": "FMA14332",
    "r_common_iliac_vein": "FMA21387",
    "l_common_iliac_vein": "FMA21388",
    "pulmonary_vein":      "FMA66643",
}

# Parts fetched for the coordinate fit. The aorta gives the three most reliable correspondences
# between real anatomy and the app's hand-drawn frame: root, arch apex, and bifurcation.
FIT_PARTS = ["FMA3736", "FMA3768", "FMA3784", "FMA3941", "FMA4058", "FMA14765", "FMA14766"]


# ── App vessel id -> real source part ─────────────────────────────────────────
# fma          an FMA id, or a list of primitive ids where a composite carries more than the
#              vessel the name means.
# seed_axis /  the vertex the centerline starts from: the vessel's proximal end.
# seed_sign    axis 0=X, 1=Y, 2=Z, in SOURCE coordinates (un-mirrored, so -X is the subject's
#              RIGHT and -Y is anterior). sign +1 max, -1 min, 0 nearest the mean.
# side         "right"/"left" restricts the trace to one side of the source midline — how a
#              single mesh holding both pulmonary arteries yields two named vessels.
# max_len_mm   stops the trace at that geodesic distance, separating a vessel's extrapulmonary
#              course from its ramification inside the lung. Values are ordinary textbook
#              lengths for the named segment, not measurements of this specimen.
VESSEL_SOURCES = {
    "ascending_aorta":     dict(fma="FMA3736",  seed_axis=2, seed_sign=-1, mode="single"),
    "aortic_arch":         dict(fma="FMA3768",  seed_axis=2, seed_sign=-1, mode="single"),
    "descending_aorta":    dict(fma="FMA3784",  seed_axis=2, seed_sign=+1, mode="single"),
    "r_common_carotid":    dict(fma="FMA3941",  seed_axis=2, seed_sign=-1, mode="single"),
    "l_common_carotid":    dict(fma="FMA4058",  seed_axis=2, seed_sign=-1, mode="single"),
    "r_subclavian_artery": dict(fma="FMA3953",  seed_axis=0, seed_sign=-1, mode="single"),
    "l_subclavian_artery": dict(fma="FMA4694",  seed_axis=0, seed_sign=+1, mode="single"),
    "hepatic_artery":      dict(fma="FMA14771", seed_axis=0, seed_sign=-1, mode="single"),
    "splenic_artery":      dict(fma="FMA14773", seed_axis=0, seed_sign=-1, mode="single"),
    "r_renal_artery":      dict(fma="FMA14752", seed_axis=0, seed_sign=-1, mode="single"),
    "l_renal_artery":      dict(fma="FMA14753", seed_axis=0, seed_sign=+1, mode="single"),
    "r_coronary_artery":   dict(fma="FMA3802",  seed_axis=2, seed_sign=+1, mode="single"),
    # stem + anterior interventricular branch (the LAD) — what "left coronary artery" means
    # the anterior interventricular branch (LAD) — the stem is a separate, unwelded shell,
    # and the LAD is the course "left coronary artery" means on a figure like this
    "l_coronary_artery":   dict(fma="FMA3862nsn", seed_axis=2, seed_sign=+1, mode="single"),
    "r_common_iliac":      dict(fma="FMA14765", seed_axis=2, seed_sign=+1, mode="single"),
    "l_common_iliac":      dict(fma="FMA14766", seed_axis=2, seed_sign=+1, mode="single"),
    "inferior_vena_cava":  dict(fma="FMA10951", seed_axis=2, seed_sign=-1, mode="single"),
    "superior_vena_cava":  dict(fma="FMA4720",  seed_axis=2, seed_sign=+1, mode="single"),
    "r_jugular_vein":      dict(fma="FMA4754",  seed_axis=2, seed_sign=-1, mode="single"),
    "l_jugular_vein":      dict(fma="FMA4762",  seed_axis=2, seed_sign=-1, mode="single"),
    # One mesh holds the trunk and both pulmonary arteries plus their intrapulmonary branches,
    # so each named vessel is a side-restricted, length-capped course through it.
    "pulmonary_trunk":     dict(fma="FMA66326", seed_axis=2, seed_sign=-1, mode="single",
                                max_len_mm=55),
    "r_pulmonary_artery":  dict(fma="FMA66326", seed_axis=2, seed_sign=-1, mode="axis",
                                side="right", side_span_mm=60, axis=0, axis_sign=-1, smooth_passes=6),
    "l_pulmonary_artery":  dict(fma="FMA66326", seed_axis=2, seed_sign=-1, mode="axis",
                                side="left", side_span_mm=60, axis=0, axis_sign=+1, smooth_passes=6),
    "r_pulmonary_vein":    dict(fma="FMA66643", seed_axis=0, seed_sign=0,  mode="axis",
                                side="right", side_span_mm=60, axis=0, axis_sign=-1, smooth_passes=6),
    "l_pulmonary_vein":    dict(fma="FMA66643", seed_axis=0, seed_sign=0,  mode="axis",
                                side="left", side_span_mm=60, axis=0, axis_sign=+1, smooth_passes=6),
}

# App vessels with no counterpart in this source. BodyParts3D segments no limb arteries, no
# cerebral arteries, no portal/hepatic veins and no lymphatics — verified, not assumed. These
# stay hand-authored, are seated inside the real body by limbs.py, and are labelled
# provenance="schematic" so the distinction is visible in the app rather than buried here.
SCHEMATIC_VESSELS = [
    "r_brachial_artery", "l_brachial_artery",
    "r_femoral_artery", "l_femoral_artery",
    "r_femoral_vein", "l_femoral_vein",
    "hepatic_vein", "portal_vein",
    "thoracic_duct", "r_lymphatic_duct",
    "renal_arteriole", "hepatic_arteriole", "mesenteric_arteriole",
]


def all_ids():
    """Every FMA id the pipeline needs to extract, de-duplicated."""
    ids = set(BODY) | set(HEART)
    ids |= {fma for fma, _ in ORGANS.values()}
    ids |= set(ARTERIES.values()) | set(VEINS.values())
    ids |= set(FIT_PARTS)
    ids |= {v["fma"] for v in VESSEL_SOURCES.values()}
    return sorted(ids)


ATTRIBUTION = (
    "BodyParts3D, (c) The Database Center for Life Science "
    "licensed under CC Attribution-Share Alike 2.1 Japan"
)
