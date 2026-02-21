# 🫀 Wall Shear Stress in the Human Circulatory System — Interactive 3D Visualization

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://python.org)
[![Plotly](https://img.shields.io/badge/Plotly-Interactive-orange.svg)](https://plotly.com)

> **An interactive 3D visualization mapping wall shear stress (WSS) distributions across the human circulatory system, based on published hemodynamic data.**

## 🔗 [Live Interactive Demo](https://your-username.github.io/shear-stress-3d-viz/)

<!-- Replace with actual GitHub Pages URL after deployment -->

---

## Overview

This visualization accompanies the review article:

> **"Resolving the Biomechanical Blind Spot in Nanomedicine Translation"**
> Modh H, Leong D, Dindhoria K, Malinovskaya J, Pirola S, Wendt B, Wacker MG.
> *ACS Nano*, 2025.

Circulating nanocarriers navigate a complex mechanical landscape where wall shear stress varies by **four orders of magnitude** — from 0.1 dyne/cm² in hepatic sinusoids to over 1000 dyne/cm² in stenotic regions. This tool allows researchers to explore these hemodynamic forces interactively.

### Features
- 🧬 **Semi-transparent body outline** with anatomically positioned organs
- 🔴 **35+ vessel segments** (arteries, veins, lymphatics, arterioles)
- 🎨 **Logarithmic WSS color mapping** from 0.1 to 1000+ dyne/cm²
- 📍 **Pathological markers** (atherosclerotic sites, stenotic hotspots, tumor vasculature)
- 🫁 **Microvascular beds** (hepatic sinusoids rendered as scatter clouds)
- ❤️ **Interactive**: rotate, zoom, hover for WSS data, toggle vessel groups
- 📄 **Single HTML file** — no server required

---

## Wall Shear Stress Data

All WSS values are sourced from peer-reviewed hemodynamic literature:

| Vascular Region | WSS (dyne/cm²) | Physiological Significance |
|:---|:---:|:---|
| Hepatic sinusoids | 0.1–0.6 | Ultra-low; fenestrated endothelium enables NP access |
| Lymphatic vessels | 0.1–0.6 | Near-stagnant drainage flow |
| Venous circulation | 1–6 | Low-pressure, high-capacitance return |
| Atherosclerotic sites | <4 | Pathological; promotes plaque formation |
| Carotid arteries | 10–20 | Physiological; maintains endothelial homeostasis |
| Arterioles | ~55 | High shear; drives nanoparticle margination |
| General arterial | 10–70 | Pulsatile systemic circulation |
| Stenotic regions | >100–1000+ | Extreme; ruptures soft lipid bilayers |

---

## Quick Start

### Prerequisites
- Python 3.8+
- pip

### Installation & Generation

```bash
# Clone the repository
git clone https://github.com/your-username/shear-stress-3d-viz.git
cd shear-stress-3d-viz

# Install dependencies
pip install -r requirements.txt

# Generate the visualization
python generate_viz.py
```

The script generates `docs/index.html` — open it in any modern browser.

### Deploy to GitHub Pages

1. Push the repository to GitHub
2. Go to **Settings → Pages**
3. Set Source: **Deploy from a branch**
4. Select branch: `main`, folder: `/docs`
5. Your visualization will be live at `https://<username>.github.io/shear-stress-3d-viz/`

---

## How It Works

The entire visualization is **programmatically generated** — no external mesh files or 3D model downloads required.

| Component | Method |
|:---|:---|
| Body outline | 14 parametric ellipsoids (torso, head, limbs) at 6% opacity |
| Blood vessels | Tube meshes via Rotation-Minimizing Frames (RMF) around cubic spline paths |
| Sinusoidal beds | Stochastic scatter point clouds in ellipsoidal volumes |
| Color mapping | Logarithmic scale: `log₁₀(WSS)` mapped to blue→cyan→green→yellow→orange→red→purple |
| Pathological sites | Diamond markers with hover annotations |
| Export | Plotly HTML with CDN-loaded JavaScript (~300 KB) |

---

## Project Structure

```
shear-stress-3d-viz/
├── generate_viz.py        # Main script (~600 lines, fully self-contained)
├── docs/
│   └── index.html         # Generated interactive visualization
├── requirements.txt       # plotly, numpy, scipy
├── LICENSE                # MIT
└── README.md              # This file
```

---

## Technical Details

### Coordinate System
- **Origin**: Navel (umbilicus)
- **X**: Left/Right (±35 cm)
- **Y**: Anterior/Posterior (±15 cm)
- **Z**: Superior/Inferior (−85 to +85 cm)
- **Units**: Centimeters

### Tube Mesh Algorithm
Vessels are rendered as triangulated tube meshes using:
1. **Cubic spline interpolation** of anatomical control points
2. **Rotation-Minimizing Frames (RMF)** via double-reflection method to prevent twist
3. **Parametric ring generation** (12 vertices per cross-section × 50 along path)
4. **Triangle strip connectivity** for efficient WebGL rendering

### Color Scale
The WSS range spans 4 orders of magnitude (0.1–1000+ dyne/cm²), requiring a logarithmic color mapping:

```
Deep Blue (0.1) → Cyan (1) → Green (3) → Yellow (10) → Orange (30) → Red (100) → Purple (1000)
```

---

## Citation

If you use this visualization in your work, please cite:

```bibtex
@article{modh2025biomechanical,
  title={Resolving the Biomechanical Blind Spot in Nanomedicine Translation},
  author={Modh, Harshvardhan and Leong, Dylan and Dindhoria, Kiran and
          Malinovskaya, Julia and Pirola, Selene and Wendt, Bernd and
          Wacker, Matthias Gerhard},
  journal={ACS Nano},
  year={2025},
  publisher={American Chemical Society}
}
```

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <i>Developed at the National University of Singapore, Department of Pharmacy and Pharmaceutical Sciences</i>
</p>
