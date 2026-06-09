"""
allowed_wss.py — the allowlist of defensible wall-shear-stress (WSS) magnitudes.

Every numeric WSS value that appears in the generated scenarios / journey / panels / spectrum
MUST be drawn from this list. The list encodes representative magnitudes consistent with the
hemodynamics & nanomedicine literature (organ/region WSS bands, benchtop "shear gap" values,
and the nanocarrier shear thresholds). It is the single gate that keeps fabricated, condition-
specific numbers out of the visualization.

All values are in dyne/cm². (0.05 Pa is stored as its dyne/cm² equivalent, 0.5.)
"""

# Region / organ healthy WSS band endpoints (dyne/cm²)
REGION_WSS = {
    "sinusoid_lo": 0.1,
    "sinusoid_hi": 0.6,
    "lymphatic_lo": 0.1,
    "lymphatic_hi": 0.6,
    "venous_lo": 1.0,
    "venous_hi": 6.0,
    "carotid_lo": 10.0,
    "carotid_hi": 15.0,
    "laminar_lo": 10.0,
    "laminar_hi": 20.0,
    "arterial_lo": 10.0,
    "arterial_hi": 70.0,
    "arteriole": 55.0,
    "atheroprone_threshold": 4.0,   # < 4 dyne/cm^2 low/oscillatory
    "stenosis_ceiling": 1000.0,     # ">1000" open-ended sentinel
}

# Regime bin boundaries (dyne/cm²)
REGIME_BINS = {"low": 25.0, "moderate": 60.0}  # low < 25, moderate 25-60, high > 60

# Nanocarrier shear-STRESS thresholds used in the journey (dyne/cm²)
NANO_THRESHOLDS = {
    "max_uptake": 0.5,       # endothelial NP uptake maximal at ~0.05 Pa = 0.5 dyne/cm^2
    "uptake_transition": 1.8,
    "rupture": 1000.0,       # > 1000 dyne/cm^2 strips hydration shells / ruptures soft bilayers
}

# Benchtop "shear gap" reference (dyne/cm²) — average shear of common in-vitro release assays
SHEAR_GAP = {
    "orbital_shaking": 0.17,
    "magnetic_stirring": 0.29,
    "dialysis_bag": 0.30,
    "microfluidic": 7.5,
    "physiological": 1000.0,  # ">1000"
}

# Spectrum decade markers (dyne/cm²)
SPECTRUM_MARKERS = [0.1, 1.0, 10.0, 100.0, 1000.0]


def _collect():
    vals = set()
    for d in (REGION_WSS, NANO_THRESHOLDS, SHEAR_GAP):
        vals.update(float(v) for v in d.values())
    vals.update(float(v) for v in REGIME_BINS.values())
    vals.update(float(v) for v in SPECTRUM_MARKERS)
    # A few intermediate region means that legitimately render (mean of allowed bands)
    vals.update({3.0, 0.3, 100.0, 40.0, 30.0})
    return vals


ALLOWED_WSS = _collect()

# Numbers that must NEVER appear anywhere (fabricated condition-specific values from the old repo)
FORBIDDEN_NUMBERS = {96, 90, 75, 18, 500, 800, 400, 600, 5000}


def is_allowed(value, tol=1e-6):
    """True if a numeric WSS value is on the allowlist (within tolerance)."""
    return any(abs(float(value) - a) <= tol for a in ALLOWED_WSS)
