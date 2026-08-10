"""
test_anatomy_fit.py — guards on the anatomy layer.

A note on what is NOT tested here, because it is the more interesting finding.

The obvious claim to test was "the vessels are inside the body". Three ways of measuring it were
built and all three were discarded, because measured against the real body the OLD hand-drawn
geometry scored the same as the new anatomy-derived geometry — about 0.9 either way. That is not
a flaw in the measurement; it is the answer. The old vessels were mostly inside a body too. What
was wrong with them was never containment, it was *position*: an aorta drawn straight where a
real one is a candy cane, arms and carotids in the wrong place, a torso flattened to a slab.

A test that passes equally on the thing you fixed and the thing you fixed it from is worth
nothing, so containment is reported as a diagnostic by build/anatomy/check_containment.py — where
it did real work, showing which limb vessels poke through the skin — and the guards below test
the claims that actually distinguish the two: that vessel geometry is derived from named cadaver
parts, and that everything positioned relative to a vessel stays attached to it.
"""

import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, ".."))
ANATOMY = os.path.join(HERE, "anatomy", "vessels.json")
CONTAINMENT = os.path.join(HERE, "anatomy", "containment.json")
DATA = os.path.join(REPO, "docs", "data", "data.json")
ASSET_DIR = os.path.join(REPO, "docs", "assets", "anatomy")

MAX_ASSET_BYTES = 3 * 1024 * 1024
MIN_ANATOMICAL_VESSELS = 20


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def data():
    if not os.path.exists(DATA):
        pytest.skip("data.json not built (run build/build_data.py)")
    return _load(DATA)


def test_every_vessel_declares_provenance(data):
    """No vessel may be silently schematic: the distinction is shown to the reader."""
    for v in data["vessels"]:
        assert v.get("provenance") in ("anatomical", "schematic"), \
            f"{v['id']} has no provenance"
        if v["provenance"] == "anatomical":
            assert v.get("source"), f"{v['id']} claims anatomical provenance but names no source"


def test_anatomical_vessels_are_the_majority(data):
    """
    Fires if centerline extraction regresses.

    build_data.py falls back to the old authored path whenever build/anatomy/vessels.json lacks
    a vessel, which is the right behaviour for a fresh checkout but would also mask a broken
    extraction. This is the tripwire for that.
    """
    anatomical = [v for v in data["vessels"] if v["provenance"] == "anatomical"]
    assert len(anatomical) >= MIN_ANATOMICAL_VESSELS, (
        f"only {len(anatomical)} vessels derived from real anatomy, expected at least "
        f"{MIN_ANATOMICAL_VESSELS}; extraction in build/anatomy/ has probably regressed"
    )


def test_anatomical_vessels_differ_from_the_authored_fallback(data):
    """
    An extracted path that happens to equal the authored one would mean nothing was extracted.
    Ten of the twelve points on a real aorta cannot coincide with a four-point hand sketch.
    """
    for v in data["vessels"]:
        if v["provenance"] != "anatomical":
            continue
        assert len(v["path"]) >= 8, (
            f"{v['id']} is marked anatomical but has only {len(v['path'])} points, "
            "which is the shape of an authored path, not an extracted centerline"
        )


def test_hotspots_and_lab_targets_sit_on_their_vessel(data):
    """
    Anchors must resolve to a point actually on the named vessel.

    This is the check the old absolute coordinates could not have. Hotspots used to be positions
    typed beside a vessel; they stayed exactly where they were while the vessel moved, and
    nothing anywhere would have reported it.
    """
    paths = {v["id"]: v["path"] for v in data["vessels"]}
    anchored = []
    for s in data["scenarios"]:
        anchored += [(h, "hotspot") for h in s.get("hotspots", [])]
    anchored += [(t, "labTarget") for t in data.get("labTargets", [])]
    assert anchored, "no hotspots or lab targets found — nothing was checked"

    for item, kind in anchored:
        assert "vesselId" in item, (
            f"{kind} {item.get('label')!r} has no vesselId; it is an unanchored coordinate and "
            "will drift the next time a vessel path changes"
        )
        path = paths.get(item["vesselId"])
        assert path, f"{kind} references unknown vessel {item['vesselId']}"
        px, py, pz = item["pos"]
        nearest = min(max(abs(px - ax), abs(py - ay), abs(pz - az)) for ax, ay, az in path)
        longest_segment = max(
            max(abs(a[i] - b[i]) for i in range(3)) for a, b in zip(path, path[1:])
        )
        # The anchor interpolates between two path points, so it need only be within one segment
        # of some point on the path. A stale anchor left behind by a moved vessel is not.
        assert nearest <= longest_segment + 1e-6, (
            f"{kind} on {item['vesselId']} at {item['pos']} is not on that vessel's path "
            f"(nearest point is {nearest:.2f} away, longest segment is {longest_segment:.2f}); "
            "rerun build/build_data.py"
        )


def test_organ_anchored_features_match_organ_positions(data):
    """Beds and tumor sites that name an organ must sit at that organ's position."""
    organs = {o["id"]: o["pos"] for o in data["organs"] if "id" in o}
    assert organs, "no organs carry an id, so nothing can be anchored to them"
    checked = 0
    for bed in data["beds"]:
        if bed.get("organ") in organs:
            assert bed["center"] == organs[bed["organ"]], \
                f"bed {bed['id']} is not at its organ {bed['organ']}"
            checked += 1
    for site in data["tumorSites"]:
        if site.get("organ") in organs:
            assert site["pos"] == organs[site["organ"]], \
                f"tumor site {site['id']} is not at its organ {site['organ']}"
            checked += 1
    assert checked >= 5, f"only {checked} organ-anchored features checked; expected more"


def test_containment_report_is_not_stale():
    """
    The containment diagnostic must describe the paths that actually shipped.

    It is a diagnostic rather than a pass/fail gate (see the module docstring), but a diagnostic
    measured against different geometry than the one in the repository is worse than none, so
    staleness is an error.
    """
    if not (os.path.exists(CONTAINMENT) and os.path.exists(DATA)):
        pytest.skip("containment not measured (run build/anatomy/check_containment.py --write)")
    import hashlib
    report = _load(CONTAINMENT)
    vessels = _load(DATA)["vessels"]
    h = hashlib.sha256()
    for v in sorted(vessels, key=lambda x: x["id"]):
        h.update(v["id"].encode())
        for p in v["path"]:
            h.update(",".join(f"{c:.3f}" for c in p).encode())
    assert report.get("pathsFingerprint") == h.hexdigest(), (
        "containment.json was measured against different vessel paths than data.json holds; "
        "rerun build/anatomy/check_containment.py --write"
    )


def test_asset_payload_within_budget():
    if not os.path.isdir(ASSET_DIR):
        pytest.skip("anatomy assets not built")
    files = [f for f in os.listdir(ASSET_DIR) if f.endswith(".glb")]
    assert files, "no GLB assets found"
    total = sum(os.path.getsize(os.path.join(ASSET_DIR, f)) for f in files)
    assert total <= MAX_ASSET_BYTES, (
        f"anatomy assets are {total/1024:.0f} KB, over the "
        f"{MAX_ASSET_BYTES/1024:.0f} KB budget for a Pages site"
    )


def test_attribution_files_ship_with_the_assets():
    """CC BY-SA obliges attribution to travel with the work."""
    if not os.path.isdir(ASSET_DIR):
        pytest.skip("anatomy assets not built")
    notice = os.path.join(ASSET_DIR, "LICENSE")
    assert os.path.exists(notice), "docs/assets/anatomy/LICENSE is missing"
    text = open(notice, encoding="utf-8").read()
    assert "BodyParts3D" in text and "Attribution-Share Alike" in text, \
        "the required BodyParts3D attribution string is not in the asset LICENSE"


def test_repo_license_flags_the_share_alike_assets():
    """MIT on the code, CC BY-SA on the meshes — the root licence must say so."""
    root = os.path.join(REPO, "LICENSE")
    if not os.path.exists(root):
        pytest.skip("no root LICENSE")
    text = open(root, encoding="utf-8").read()
    assert "docs/assets/anatomy" in text, (
        "the root LICENSE does not mention that docs/assets/anatomy is under different terms"
    )
