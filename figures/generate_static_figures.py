#!/usr/bin/env python3
"""Static figure generator for the wall shear stress (WSS) hemodynamic dataset.

Reads the canonical data file ``docs/data/data.json`` and renders a set of
clean, decluttered, publication-grade static figures of wall shear stress
across the human circulatory system.

All numbers (WSS values, vessel geometry, scenario blurbs, panel data) come
from ``data.json`` only — nothing is hardcoded or invented here. WSS magnitudes
are representative values consistent with the hemodynamics & nanomedicine
literature.

Outputs (PNG @ 300 dpi + PDF) into the ``figures/`` directory:
  1. wss_map.{png,pdf}    — main coronal map of all vessels coloured by WSS
  2. scenarios.{png,pdf}  — small-multiples grid of the 5 scenarios
  3. spectrum.{png,pdf}   — standalone horizontal log WSS spectrum bar
  4. shear_gap.{png,pdf}  — the "Shear Gap" benchtop-vs-physiological chart

Run:  python3 figures/generate_static_figures.py
"""

from __future__ import annotations

import json
import math
import textwrap
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")  # headless / file output only
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.patches import FancyArrowPatch
import matplotlib.patheffects as pe

# Optional smoother spline path (graceful fallback to numpy interp if missing).
try:
    from scipy.interpolate import CubicSpline  # type: ignore

    _HAVE_SCIPY = True
except Exception:  # pragma: no cover - environment without scipy
    _HAVE_SCIPY = False


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_PATH = ROOT / "docs" / "data" / "data.json"
OUT_DIR = HERE


# --------------------------------------------------------------------------- #
# Theme (cohesive dark theme matching the web app)
# --------------------------------------------------------------------------- #
BG = "#0b0e16"          # page / axes background
TEXT = "#e8eef7"        # primary light text
MUTED = "#93a4bd"       # secondary / muted text
ACCENT = "#36d0e0"      # teal accent
PANEL = "#11151f"       # slightly lighter panel fill
GRIDLINE = "#1d2435"  # subtle grid / spine colour

# Hotspot kind -> glow colour
HOTSPOT_COLORS = {
    "plaque": "#ffcc33",    # gold
    "stenosis": "#ff3b30",  # red
    "tumor": "#ff3df0",     # magenta
}


def _set_sans_serif() -> None:
    """Pick a clean sans-serif that exists on the system."""
    preferred = [
        "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans",
        "Liberation Sans", "Nimbus Sans",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = [name for name in preferred if name in available] or ["DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = chosen + plt.rcParams["font.sans-serif"]


def _apply_theme() -> None:
    _set_sans_serif()
    plt.rcParams.update({
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
        "axes.facecolor": BG,
        "axes.edgecolor": GRIDLINE,
        "axes.labelcolor": TEXT,
        "text.color": TEXT,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.titlecolor": TEXT,
        "figure.dpi": 110,
        "savefig.dpi": 300,
    })


# --------------------------------------------------------------------------- #
# Data loading + colormap
# --------------------------------------------------------------------------- #
def load_data() -> dict:
    with open(DATA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_cmap(colorscale: list[dict]) -> LinearSegmentedColormap:
    """Build a LinearSegmentedColormap from the data colorscale stops."""
    stops = sorted(colorscale, key=lambda c: c["stop"])
    colors = [(c["stop"], tuple(v / 255.0 for v in c["rgb"])) for c in stops]
    return LinearSegmentedColormap.from_list("wss", colors, N=512)


def wss_to_pos(wss: float, log_min: float, log_max: float) -> float:
    """Map a WSS value to a 0..1 colormap position on the log scale."""
    w = max(float(wss), 1e-6)
    pos = (math.log10(w) - log_min) / (log_max - log_min)
    return float(min(max(pos, 0.0), 1.0))


# --------------------------------------------------------------------------- #
# Geometry helpers (project 3D -> 2D coronal view: X horizontal, Z vertical)
# --------------------------------------------------------------------------- #
def smooth_path_xz(path: list[list[float]], n: int = 200) -> tuple[np.ndarray, np.ndarray]:
    """Return smoothed (x, z) arrays for a vessel path (coronal projection)."""
    pts = np.asarray(path, dtype=float)
    x, z = pts[:, 0], pts[:, 2]
    if len(pts) < 3:
        # too few points to spline; linear densify
        t = np.linspace(0.0, 1.0, len(pts))
        tt = np.linspace(0.0, 1.0, n)
        return np.interp(tt, t, x), np.interp(tt, t, z)

    # Parameterise by cumulative chord length for a stable spline.
    seg = np.sqrt(np.diff(x) ** 2 + np.diff(z) ** 2)
    t = np.concatenate([[0.0], np.cumsum(seg)])
    if t[-1] == 0:
        return x, z
    t = t / t[-1]
    tt = np.linspace(0.0, 1.0, n)

    if _HAVE_SCIPY:
        xs = CubicSpline(t, x)(tt)
        zs = CubicSpline(t, z)(tt)
    else:  # numpy fallback
        xs = np.interp(tt, t, x)
        zs = np.interp(tt, t, z)
    return xs, zs


def mean_wss(vessel: dict) -> float:
    """Geometric mean of the vessel's [lo, hi] WSS range (log-domain centre)."""
    lo, hi = vessel["wss"]
    return math.sqrt(max(lo, 1e-6) * max(hi, 1e-6))


def radius_to_lw(radius: float, rmin: float, rmax: float,
                 lw_min: float = 1.4, lw_max: float = 7.0) -> float:
    """Map vessel radius to a readable, clamped line width."""
    if rmax <= rmin:
        return (lw_min + lw_max) / 2.0
    frac = (radius - rmin) / (rmax - rmin)
    frac = min(max(frac, 0.0), 1.0)
    # sqrt keeps thin vessels visible without making big ones overwhelming
    return lw_min + (lw_max - lw_min) * math.sqrt(frac)


def colored_vessel_segments(xs: np.ndarray, zs: np.ndarray,
                            color) -> LineCollection:
    """Build a LineCollection for a single-colour smooth vessel line."""
    pts = np.array([xs, zs]).T.reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    lc = LineCollection(segs, colors=[color], capstyle="round",
                        joinstyle="round")
    return lc


def data_bounds(vessels: list[dict]) -> tuple[float, float, float, float]:
    xs, zs = [], []
    for v in vessels:
        p = np.asarray(v["path"], dtype=float)
        xs.extend(p[:, 0].tolist())
        zs.extend(p[:, 2].tolist())
    return min(xs), max(xs), min(zs), max(zs)


# --------------------------------------------------------------------------- #
# Shared vessel renderer
# --------------------------------------------------------------------------- #
def draw_vasculature(ax, vessels, cmap, log_min, log_max,
                     wss_override: dict | None = None,
                     dim_unaffected: bool = False,
                     affected_ids: set | None = None,
                     base_alpha: float = 1.0,
                     glow: bool = True) -> None:
    """Draw all vessels coloured by (possibly overridden) mean WSS.

    wss_override : {vessel_id: wss_value} recolours specific vessels.
    dim_unaffected : if True, vessels not in affected_ids are dimmed.
    """
    radii = [v["radius"] for v in vessels]
    rmin, rmax = min(radii), max(radii)
    norm = Normalize(vmin=0.0, vmax=1.0)
    affected_ids = affected_ids or set()

    for v in vessels:
        xs, zs = smooth_path_xz(v["path"])
        if wss_override and v["id"] in wss_override:
            w = wss_override[v["id"]]
        else:
            w = mean_wss(v)
        pos = wss_to_pos(w, log_min, log_max)
        color = cmap(norm(pos))
        lw = radius_to_lw(v["radius"], rmin, rmax)

        is_affected = v["id"] in affected_ids
        alpha = base_alpha
        if dim_unaffected and not is_affected:
            alpha = base_alpha * 0.22

        # soft glow underlay for depth
        if glow and alpha > 0.5:
            glow_lc = colored_vessel_segments(xs, zs, color)
            glow_lc.set_linewidth(lw + 3.2)
            glow_lc.set_alpha(0.10 * alpha)
            ax.add_collection(glow_lc)

        lc = colored_vessel_segments(xs, zs, color)
        lc.set_linewidth(lw)
        lc.set_alpha(alpha)
        ax.add_collection(lc)


def draw_hotspots(ax, hotspots) -> None:
    """Draw glowing markers at hotspot positions (coronal X/Z projection)."""
    for h in hotspots:
        x, _y, z = h["pos"]
        color = HOTSPOT_COLORS.get(h["kind"], ACCENT)
        # layered glow
        for r, a in [(420, 0.10), (230, 0.18), (120, 0.30)]:
            ax.scatter([x], [z], s=r, color=color, alpha=a,
                       edgecolors="none", zorder=5)
        ax.scatter([x], [z], s=46, color=color, alpha=0.95,
                   edgecolors=BG, linewidths=0.8, zorder=6)


def add_body_silhouette(ax, vessels, pad_x=5.0, pad_z=8.0) -> None:
    """Faint soft grey rounded silhouette approximated from the bounding box."""
    from matplotlib.patches import FancyBboxPatch

    x0, x1, z0, z1 = data_bounds(vessels)
    w = (x1 - x0) + 2 * pad_x
    h = (z1 - z0) + 2 * pad_z
    patch = FancyBboxPatch(
        (x0 - pad_x, z0 - pad_z), w, h,
        boxstyle="round,pad=0,rounding_size=10",
        facecolor="#10151f", edgecolor="#1a2030",
        linewidth=1.0, alpha=0.45, zorder=0,
    )
    ax.add_patch(patch)


# --------------------------------------------------------------------------- #
# Colorbar helper
# --------------------------------------------------------------------------- #
LOG_TICKS = [0.1, 1.0, 10.0, 100.0, 1000.0]


def add_wss_colorbar(fig, cmap, log_min, log_max, unit,
                     orientation="vertical", ax=None, cax=None,
                     label_fontsize=11, tick_fontsize=10):
    norm = Normalize(vmin=0.0, vmax=1.0)
    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    tick_pos = [wss_to_pos(t, log_min, log_max) for t in LOG_TICKS]
    tick_lab = [("0.1" if t == 0.1 else f"{int(t)}") for t in LOG_TICKS]

    kw = dict(orientation=orientation)
    if cax is not None:
        kw["cax"] = cax
    elif ax is not None:
        kw["ax"] = ax
    cb = fig.colorbar(sm, **kw)
    if orientation == "vertical":
        cb.set_ticks(tick_pos)
        cb.set_ticklabels(tick_lab)
        cb.ax.tick_params(labelsize=tick_fontsize, colors=MUTED)
        cb.set_label(f"Wall shear stress  ({unit}, log scale)",
                     color=TEXT, fontsize=label_fontsize)
    else:
        cb.set_ticks(tick_pos)
        cb.set_ticklabels(tick_lab)
        cb.ax.tick_params(labelsize=tick_fontsize, colors=MUTED)
        cb.set_label(f"Wall shear stress  ({unit}, log scale)",
                     color=TEXT, fontsize=label_fontsize)
    cb.outline.set_edgecolor(GRIDLINE)
    return cb


def save(fig, stem: str) -> list[Path]:
    written = []
    for ext in ("png", "pdf"):
        path = OUT_DIR / f"{stem}.{ext}"
        fig.savefig(path, facecolor=BG, bbox_inches="tight")
        written.append(path)
    plt.close(fig)
    return written


# --------------------------------------------------------------------------- #
# Figure 1 — main WSS map
# --------------------------------------------------------------------------- #
# Key regions to annotate in the margins (id, label, side).
# Leader lines are drawn from the vessel to a label placed clear of geometry.
KEY_LABELS = [
    ("ascending_aorta", "Aorta", "left"),
    ("r_common_carotid", "Carotid", "right"),
    ("inferior_vena_cava", "Vena cava", "right"),
    ("r_femoral_artery", "Femoral artery", "right"),
    ("thoracic_duct", "Thoracic duct (lymphatic)", "left"),
    ("renal_arteriole", "Renal arteriole", "right"),
]


def _vessel_midpoint_xz(vessel) -> tuple[float, float]:
    p = np.asarray(vessel["path"], dtype=float)
    mid = p[len(p) // 2]
    return float(mid[0]), float(mid[2])


def figure_wss_map(data, cmap) -> list[Path]:
    meta = data["meta"]
    log_min, log_max = meta["logMin"], meta["logMax"]
    vessels = data["vessels"]
    beds = data.get("beds", [])

    fig, ax = plt.subplots(figsize=(11, 13))
    add_body_silhouette(ax, vessels)
    draw_vasculature(ax, vessels, cmap, log_min, log_max)

    # Low-shear sinusoidal beds as soft halos (use their representative WSS).
    norm = Normalize(0, 1)
    for bed in beds:
        cx, _cy, cz = bed["center"]
        sx, _sy, sz = bed["spread"]
        bw = mean_wss(bed)
        bcolor = cmap(norm(wss_to_pos(bw, log_min, log_max)))
        for scale, a in [(2.2, 0.06), (1.5, 0.10), (1.0, 0.16)]:
            ax.scatter([cx], [cz], s=(max(sx, sz) * 90 * scale) ** 1.0,
                       color=bcolor, alpha=a, edgecolors="none", zorder=1)

    x0, x1, z0, z1 = data_bounds(vessels)
    ax.set_xlim(x0 - 12, x1 + 12)
    ax.set_ylim(z0 - 12, z1 + 12)
    ax.set_aspect("equal")
    ax.axis("off")

    by_id = {v["id"]: v for v in vessels}
    xmin, xmax = ax.get_xlim()
    label_fx = {
        "left": xmin + 0.5,
        "right": xmax - 0.5,
    }
    # vertical staggering so the margin labels never collide
    left_slots = [z for z in np.linspace(z1 + 6, z0 - 6, 8)]
    right_slots = [z for z in np.linspace(z1 + 6, z0 - 6, 8)]
    li = ri = 0
    for vid, label, side in KEY_LABELS:
        if vid not in by_id:
            continue
        vx, vz = _vessel_midpoint_xz(by_id[vid])
        if side == "left":
            tx, tz = label_fx["left"], left_slots[li]
            li += 1
            ha = "left"
        else:
            tx, tz = label_fx["right"], right_slots[ri]
            ri += 1
            ha = "right"
        ax.annotate(
            label, xy=(vx, vz), xytext=(tx, tz),
            ha=ha, va="center", fontsize=11, color=TEXT, weight="medium",
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.9,
                            alpha=0.7, shrinkA=0, shrinkB=4,
                            connectionstyle="arc3,rad=0.12"),
            path_effects=[pe.withStroke(linewidth=2.5, foreground=BG)],
            zorder=8,
        )

    fig.text(0.5, 0.965,
             "Wall Shear Stress Across the Human Circulatory System",
             ha="center", va="top", color=TEXT, fontsize=20, weight="bold")
    fig.text(0.5, 0.93,
             "Coronal view · vessels coloured by representative WSS · "
             "line width scales with vessel calibre",
             ha="center", va="top", color=MUTED, fontsize=11)

    cb = add_wss_colorbar(fig, cmap, log_min, log_max, meta["wssUnit"],
                          orientation="vertical", ax=ax, label_fontsize=12)
    cb.ax.set_position(cb.ax.get_position())

    fig.subplots_adjust(left=0.02, right=0.9, top=0.9, bottom=0.03)
    return save(fig, "wss_map")


# --------------------------------------------------------------------------- #
# Figure 2 — scenario small-multiples
# --------------------------------------------------------------------------- #
def _trim_caption(text: str, max_chars: int = 150) -> str:
    """Trim a blurb to one tidy line ending on a sentence/word boundary."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # prefer to end at a sentence boundary, else a word boundary
    for sep in (". ", "; ", "— ", ", "):
        idx = cut.rfind(sep)
        if idx > max_chars * 0.5:
            return cut[: idx + 1].strip()
    return cut.rsplit(" ", 1)[0].strip() + "…"


def _scenario_overrides(scenario) -> dict:
    """Build {vessel_id: wss_value} from a scenario's changes."""
    overrides = {}
    for ch in scenario.get("changes", []):
        if ch.get("displayWss"):
            lo, hi = ch["displayWss"]
            val = math.sqrt(max(lo, 1e-6) * max(hi, 1e-6))
        elif ch.get("sentinel") is not None:
            val = float(ch["sentinel"])
        else:
            continue
        for vid in ch.get("vessels", []):
            overrides[vid] = val
    return overrides


def figure_scenarios(data, cmap) -> list[Path]:
    meta = data["meta"]
    log_min, log_max = meta["logMin"], meta["logMax"]
    vessels = data["vessels"]
    scenarios = data["scenarios"]

    n = len(scenarios)
    ncol = 3
    nrow = math.ceil((n + 0) / ncol)  # 5 scenarios -> 2x3 (last cell empty)

    fig, axes = plt.subplots(nrow, ncol, figsize=(16, 11))
    axes = np.array(axes).reshape(-1)

    x0, x1, z0, z1 = data_bounds(vessels)

    for i, scenario in enumerate(scenarios):
        ax = axes[i]
        overrides = _scenario_overrides(scenario)
        affected = set(overrides.keys())
        dim = scenario.get("dim", False)

        draw_vasculature(
            ax, vessels, cmap, log_min, log_max,
            wss_override=overrides if overrides else None,
            dim_unaffected=dim and bool(affected),
            affected_ids=affected,
            glow=False,
        )

        # schematic tumour beds (regime-only, no measured value -> use repWss)
        norm = Normalize(0, 1)
        for bed in scenario.get("beds", []):
            cx, _cy, cz = bed["center"]
            rep = bed.get("representativeWss", 1.0)
            bcolor = cmap(norm(wss_to_pos(rep, log_min, log_max)))
            sx, _sy, sz = bed["spread"]
            for scale, a in [(2.0, 0.10), (1.3, 0.16), (0.8, 0.24)]:
                ax.scatter([cx], [cz], s=(max(sx, sz) * 80 * scale),
                           color=bcolor, alpha=a, edgecolors="none", zorder=2)

        draw_hotspots(ax, scenario.get("hotspots", []))

        ax.set_xlim(x0 - 6, x1 + 6)
        ax.set_ylim(z0 - 8, z1 + 8)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(scenario["label"], fontsize=14, color=TEXT,
                     weight="bold", pad=6)
        caption = _trim_caption(scenario["blurb"], max_chars=130)
        caption = "\n".join(textwrap.wrap(caption, width=46))
        ax.text(0.5, -0.04, caption,
                transform=ax.transAxes, ha="center", va="top",
                fontsize=8.5, color=MUTED, linespacing=1.3)

    # Use any empty cell for a shared legend of hotspot kinds.
    for j in range(n, len(axes)):
        axes[j].axis("off")

    if n < len(axes):
        legend_ax = axes[n]
        legend_ax.axis("off")
        items = [("Plaque (atherosclerosis)", HOTSPOT_COLORS["plaque"]),
                 ("Stenosis hotspot", HOTSPOT_COLORS["stenosis"]),
                 ("Tumor vasculature", HOTSPOT_COLORS["tumor"])]
        y = 0.66
        legend_ax.text(0.5, 0.86, "Hotspot legend", transform=legend_ax.transAxes,
                       ha="center", fontsize=12, color=TEXT, weight="bold")
        for text, color in items:
            legend_ax.scatter([0.18], [y], s=160, color=color,
                              transform=legend_ax.transAxes, edgecolors=BG,
                              linewidths=0.8, zorder=5)
            legend_ax.text(0.28, y, text, transform=legend_ax.transAxes,
                           ha="left", va="center", fontsize=11, color=TEXT)
            y -= 0.16
        legend_ax.text(0.5, 0.06,
                       "Affected vessels recoloured by representative WSS;\n"
                       "unaffected vessels dimmed for context.",
                       transform=legend_ax.transAxes, ha="center", va="bottom",
                       fontsize=8.5, color=MUTED, linespacing=1.3)

    fig.suptitle("Wall Shear Stress Across Disease Scenarios",
                 fontsize=21, color=TEXT, weight="bold", y=0.99)

    # Shared horizontal colorbar at the bottom.
    cbar_ax = fig.add_axes([0.30, 0.05, 0.40, 0.018])
    add_wss_colorbar(fig, cmap, log_min, log_max, meta["wssUnit"],
                     orientation="horizontal", cax=cbar_ax,
                     label_fontsize=10.5, tick_fontsize=9)

    fig.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.11,
                        wspace=0.05, hspace=0.22)
    return save(fig, "scenarios")


# --------------------------------------------------------------------------- #
# Figure 3 — WSS spectrum bar
# --------------------------------------------------------------------------- #
def figure_spectrum(data, cmap) -> list[Path]:
    meta = data["meta"]
    log_min, log_max = meta["logMin"], meta["logMax"]
    unit = meta["wssUnit"]
    markers = data["panels"]["spectrum"]

    fig, ax = plt.subplots(figsize=(14, 5.0))

    # Gradient image across the log range (x = position 0..1).
    grad = np.linspace(0, 1, 1024).reshape(1, -1)
    ax.imshow(grad, aspect="auto", cmap=cmap, extent=[0, 1, 0, 1],
              origin="lower", zorder=1)

    # Frame
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    for spine in ax.spines.values():
        spine.set_color(GRIDLINE)
        spine.set_linewidth(1.0)
    ax.set_yticks([])

    # Decade ticks on the bottom.
    tick_pos = [wss_to_pos(t, log_min, log_max) for t in LOG_TICKS]
    tick_lab = [("0.1" if t == 0.1 else f"{int(t)}") for t in LOG_TICKS]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lab, fontsize=12, color=MUTED)
    ax.tick_params(axis="x", length=5, color=GRIDLINE)
    ax.set_xlabel(f"Wall shear stress  ({unit}, log scale)",
                  fontsize=13, color=TEXT, labelpad=8)

    # Marker labels placed above the bar, alternating height to avoid overlap.
    n = len(markers)
    for i, m in enumerate(markers):
        pos = wss_to_pos(m["wss"], log_min, log_max)
        ax.axvline(pos, ymin=0, ymax=1, color=BG, lw=2.0, alpha=0.85, zorder=2)
        ax.axvline(pos, ymin=0, ymax=1, color=TEXT, lw=0.8, alpha=0.7, zorder=3)
        # value chip on the bar
        valtxt = ("0.1" if m["wss"] == 0.1 else
                  (f"{int(m['wss'])}" if float(m["wss"]).is_integer()
                   else f"{m['wss']:g}"))
        # alternate label vertical anchor to spread them out; wrap long labels
        ytext = 1.22 if i % 2 == 0 else 1.48
        lbl = "\n".join(textwrap.wrap(m["label"], width=16))
        # nudge edge labels inward so they stay on-canvas
        ha = "center"
        if i == 0:
            ha = "left"
        elif i == n - 1:
            ha = "right"
        ax.annotate(
            lbl, xy=(pos, 1.0), xytext=(pos, ytext),
            ha=ha, va="bottom", fontsize=10.5, color=TEXT,
            annotation_clip=False, linespacing=1.2,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.9, alpha=0.8),
        )
        ax.text(pos, 0.07, valtxt, ha="center", va="bottom", fontsize=10,
                color="#0b0e16", weight="bold",
                path_effects=[pe.withStroke(linewidth=2.2, foreground="#ffffff")],
                zorder=5)

    fig.text(0.5, 0.97,
             "Four Orders of Magnitude: the Wall Shear Stress Spectrum",
             ha="center", va="top", fontsize=18, color=TEXT, weight="bold")

    fig.subplots_adjust(left=0.05, right=0.97, top=0.62, bottom=0.18)
    return save(fig, "spectrum")


# --------------------------------------------------------------------------- #
# Figure 4 — the Shear Gap
# --------------------------------------------------------------------------- #
def figure_shear_gap(data, cmap) -> list[Path]:
    meta = data["meta"]
    log_min, log_max = meta["logMin"], meta["logMax"]
    unit = meta["wssUnit"]
    rows = data["panels"]["shearGap"]
    takeaway = data["panels"]["shearGapTakeaway"]

    fig, ax = plt.subplots(figsize=(13, 6.6))

    labels = [r["method"] for r in rows]
    y = np.arange(len(rows))[::-1]  # first row at top
    norm = Normalize(0, 1)
    bench_color = "#3a4763"  # muted slate for benchtop methods

    bar_h = 0.62
    for yi, r in zip(y, rows):
        shear = float(r["shear"])
        if r["kind"] == "physiological":
            # hot gradient bar built from many thin coloured segments on log-x
            x_lo = 0.1
            x_hi = shear
            xs = np.logspace(math.log10(x_lo), math.log10(x_hi), 80)
            for k in range(len(xs) - 1):
                seg_w = xs[k + 1] - xs[k]
                pos = wss_to_pos(xs[k], log_min, log_max)
                ax.barh(yi, seg_w, left=xs[k], height=bar_h,
                        color=cmap(norm(pos)), edgecolor="none", zorder=3)
            # open-ended arrow if flagged
            if r.get("openEnded"):
                arr = FancyArrowPatch(
                    (shear * 0.92, yi), (shear * 2.6, yi),
                    arrowstyle="-|>", mutation_scale=22,
                    color=cmap(norm(wss_to_pos(shear, log_min, log_max))),
                    lw=3.2, zorder=4,
                )
                ax.add_patch(arr)
                ax.text(shear * 3.0, yi, ">1000", va="center", ha="left",
                        fontsize=12, color=TEXT, weight="bold", zorder=5)
        else:
            ax.barh(yi, shear - 0.01, left=0.01, height=bar_h,
                    color=bench_color, edgecolor="#4a597a", linewidth=0.8,
                    zorder=3)
            ax.text(shear * 1.25, yi, f"{shear:g}", va="center", ha="left",
                    fontsize=11, color=MUTED, zorder=5)

    ax.set_xscale("log")
    ax.set_xlim(0.05, 4000)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=13, color=TEXT)
    ax.set_xticks(LOG_TICKS)
    ax.set_xticklabels([("0.1" if t == 0.1 else f"{int(t)}") for t in LOG_TICKS],
                       fontsize=11, color=MUTED)
    ax.set_xlabel(f"Wall shear stress  ({unit}, log scale)",
                  fontsize=13, color=TEXT, labelpad=8)

    ax.grid(axis="x", color=GRIDLINE, lw=0.8, alpha=0.6, zorder=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRIDLINE)
    ax.tick_params(axis="y", length=0)

    ax.set_title("The Shear Gap: why benchtop tests mislead",
                 fontsize=20, color=TEXT, weight="bold", pad=14)

    # Takeaway caption under the chart.
    fig.text(0.5, 0.015, takeaway, ha="center", va="bottom",
             fontsize=11, color=MUTED, wrap=True,
             linespacing=1.4)

    fig.subplots_adjust(left=0.16, right=0.96, top=0.88, bottom=0.20)
    return save(fig, "shear_gap")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    _apply_theme()
    data = load_data()
    cmap = build_cmap(data["colorscale"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    written += figure_wss_map(data, cmap)
    written += figure_scenarios(data, cmap)
    written += figure_spectrum(data, cmap)
    written += figure_shear_gap(data, cmap)

    if not _HAVE_SCIPY:
        print("[note] scipy not found — used numpy interpolation fallback.")
    print(f"Wrote {len(written)} files:")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    main()
