"""
test_build_data.py — invariants for the single-source-of-truth data layer.

Enforces schema completeness, colorscale log-linearity, referential integrity, the scientific
honesty rules (allowlist, deny-list, no WSS digits in vessel/bed notes, stenosis ceiling, single
unit), and json==js equivalence. Run:  python3 -m pytest build/ -q
"""

import json
import math
import os
import re

import build_data as bd
from allowed_wss import is_allowed, FORBIDDEN_NUMBERS

DATA = bd.build_data()
HERE = os.path.dirname(os.path.abspath(__file__))

# Regex used to forbid restated WSS numbers inside vessel/bed NOTES (not narrative copy).
WSS_DIGIT_RE = re.compile(r"\d+\s*[–\-]\s*\d+|\d+\s*dyne|~\d+")
# Numeric tokens that appear in scenario/journey/panel WSS fields, gathered for allowlist checks.


# --- Schema completeness ----------------------------------------------------
def test_top_level_keys():
    for k in ("meta", "colorscale", "groupColors", "vessels", "beds", "organs",
              "landmarks", "scenarios", "journey", "panels"):
        assert k in DATA, f"missing top-level key {k}"


def test_meta_unit():
    assert DATA["meta"]["wssUnit"] == "dyne/cm²"
    assert DATA["meta"]["logMin"] == -1.0 and DATA["meta"]["logMax"] == 3.0


def test_vessel_schema():
    ids = set()
    for v in DATA["vessels"]:
        for k in ("id", "name", "group", "path", "radius", "wss", "regime", "note"):
            assert k in v, f"vessel missing {k}: {v.get('name')}"
        assert v["id"] not in ids, f"duplicate vessel id {v['id']}"
        ids.add(v["id"])
        assert len(v["path"]) >= 2
        for p in v["path"]:
            assert len(p) == 3 and all(isinstance(c, float) for c in p)
            assert all(not math.isnan(c) for c in p)
        assert v["radius"] > 0
        lo, hi = v["wss"]
        assert 0 < lo <= hi
        assert v["regime"] in ("extreme", "low", "moderate", "high", "low_oscillatory")


# --- Colorscale -------------------------------------------------------------
def test_colorscale_monotonic_and_log_linear():
    cs = DATA["colorscale"]
    assert cs[0]["stop"] == 0.0 and abs(cs[-1]["stop"] - 1.0) < 1e-9
    prev_stop = prev_wss = -1
    for c in cs:
        assert 0.0 <= c["stop"] <= 1.0
        assert c["stop"] > prev_stop, "stops must strictly increase"
        assert c["wss"] > prev_wss, "wss must strictly increase"
        prev_stop, prev_wss = c["stop"], c["wss"]
        # log10(wss) maps linearly onto [logMin, logMax] at each stop
        expected = (math.log10(c["wss"]) - bd.LOG_MIN) / (bd.LOG_MAX - bd.LOG_MIN)
        assert abs(c["stop"] - expected) < 1e-6, f"stop/wss not log-linear at wss={c['wss']}"
        for ch in c["rgb"]:
            assert 0 <= ch <= 255


# --- Referential integrity --------------------------------------------------
def _vessel_ids():
    return {v["id"] for v in DATA["vessels"]}


def test_scenario_vessel_refs_exist():
    ids = _vessel_ids()
    for s in DATA["scenarios"]:
        for ch in s["changes"]:
            for vid in ch["vessels"]:
                assert vid in ids, f"scenario {s['id']} references unknown vessel {vid}"


def test_journey_vessel_refs_exist():
    ids = _vessel_ids()
    for wp in DATA["journey"]["waypoints"]:
        if "vesselId" in wp:
            assert wp["vesselId"] in ids, f"journey waypoint {wp['id']} unknown vessel"
        else:
            assert "pos" in wp, f"waypoint {wp['id']} needs vesselId or pos"


# --- Honesty: no WSS digits in vessel/bed notes -----------------------------
def test_notes_have_no_wss_digits():
    for v in DATA["vessels"]:
        assert not WSS_DIGIT_RE.search(v["note"]), f"vessel note restates WSS: {v['name']} -> {v['note']}"
    for b in DATA["beds"]:
        assert not WSS_DIGIT_RE.search(b["note"]), f"bed note restates WSS: {b['name']}"
    for o in DATA["organs"]:
        assert not WSS_DIGIT_RE.search(o["note"]), f"organ note restates WSS: {o['name']}"


# --- Honesty: every scenario/journey/panel WSS value is allowlisted ---------
def _scenario_panel_wss_values():
    vals = []
    for s in DATA["scenarios"]:
        for ch in s["changes"]:
            if ch.get("displayWss"):
                vals += list(ch["displayWss"])
            if ch.get("sentinel"):
                vals.append(ch["sentinel"])
        for b in s["beds"]:
            if "representativeWss" in b:
                vals.append(b["representativeWss"])
    for wp in DATA["journey"]["waypoints"]:
        vals.append(wp["shearDyne"])
    for m in DATA["panels"]["spectrum"]:
        vals.append(m["wss"])
    for g in DATA["panels"]["shearGap"]:
        vals.append(g["shear"])
    for v in DATA["panels"]["regimes"].values():
        vals.append(v)
    return vals


def test_all_scenario_panel_wss_allowlisted():
    for v in _scenario_panel_wss_values():
        assert is_allowed(v), f"WSS value {v} not on the allowlist"


def test_vessel_wss_endpoints_allowlisted():
    for v in DATA["vessels"] + DATA["beds"]:
        for endpoint in v["wss"]:
            assert is_allowed(endpoint), f"{v['name']} wss endpoint {endpoint} not allowlisted"


# --- Honesty: deny-list / stenosis ceiling / no forbidden numbers -----------
def test_no_forbidden_numbers_in_wss():
    for v in _scenario_panel_wss_values():
        assert int(round(v)) not in FORBIDDEN_NUMBERS, f"forbidden number {v} present"


def test_stenosis_ceiling_capped():
    # No stored WSS may exceed 1000 except the open-ended sentinel (== 1000 with openEnded flag).
    for v in _scenario_panel_wss_values():
        assert v <= 1000.0 + 1e-9, f"WSS {v} exceeds the >1000 ceiling"


def test_no_fabricated_percentages_in_copy():
    fab = re.compile(r"-?\d+\s*%|\b\d+\s*x\s*(increase|reduction)", re.I)
    bad = ("96", "90", "75", "18x", "10-50x")
    for s in DATA["scenarios"]:
        text = s["blurb"]
        for token in bad:
            assert token + "%" not in text and token not in re.findall(r"\d+x", text), \
                f"scenario {s['id']} blurb contains fabricated token {token}"
    # journey copy may cite allowlisted thresholds but never a fabricated %/fold
    for wp in DATA["journey"]["waypoints"]:
        m = fab.search(wp["copy"])
        # +60% permeability is permitted (it's a defensible literature value, not a WSS % delta)
        if m:
            assert "60%" in m.group(0), f"journey {wp['id']} has a fabricated %: {m.group(0)}"


# --- Single unit: all journey shear in dyne/cm² -----------------------------
def test_journey_single_unit():
    for wp in DATA["journey"]["waypoints"]:
        assert "shearDyne" in wp, f"waypoint {wp['id']} missing shearDyne"
        # shear-RATE facts only ever live in shearRateNote/copy, never as a numeric stress field
        assert "shearRate" not in wp


# --- json == js equivalence + tasks/-independence ---------------------------
def test_json_equals_js_when_built():
    bd.main()
    json_path = os.path.join(bd.OUT_DIR, "data.json")
    js_path = os.path.join(bd.OUT_DIR, "data.js")
    with open(json_path, encoding="utf-8") as f:
        from_json = json.load(f)
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    m = re.search(r"export const DATA = (.*);\s*$", js, re.S)
    assert m, "data.js does not contain the expected export"
    from_js = json.loads(m.group(1))
    assert from_json == from_js, "data.json and data.js diverged"


def test_builds_without_tasks_dir():
    # build_data.py must depend only on build/ inputs, never on the gitignored tasks/ reference.
    src = open(os.path.join(HERE, "build_data.py"), encoding="utf-8").read()
    assert "tasks/" not in src and "manuscript" not in src.lower()
