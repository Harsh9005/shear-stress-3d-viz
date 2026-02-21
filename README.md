# Wall Shear Stress in the Human Circulatory System

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://python.org)
[![Matplotlib](https://img.shields.io/badge/Matplotlib-Figures-blue.svg)](https://matplotlib.org)
[![Plotly](https://img.shields.io/badge/Plotly-Interactive_3D-orange.svg)](https://plotly.com)

> **Programmatically generated visualizations mapping wall shear stress (WSS) distributions across the human circulatory system under healthy and pathological conditions, based on published hemodynamic data.**

---

## Overview

This visualization accompanies the review article:

> **"Resolving the Biomechanical Blind Spot in Nanomedicine Translation"**
> Modh H, Leong D, Dindhoria K, Malinovskaya J, Pirola S, Wendt B, Wacker MG.
> *ACS Nano*, 2025.

Circulating nanocarriers navigate a complex mechanical landscape where wall shear stress varies by **four orders of magnitude** -- from 0.1 dyne/cm^2 in hepatic sinusoids to over 1000 dyne/cm^2 in stenotic regions. These visualizations allow researchers to explore how different pathologies reshape the hemodynamic forces that nanocarriers encounter.

---

## Scenario Gallery

Seven scenario-based figures illustrate how pathology alters the WSS landscape:

### 1. Healthy Baseline
Normal physiological WSS distribution across the circulatory system.

![Healthy Baseline](scenarios/01_healthy_baseline.png)

### 2. Lung Cancer
Tumor vasculature disrupts pulmonary hemodynamics with chaotic, low-WSS regions.

![Lung Cancer](scenarios/02_lung_cancer.png)

### 3. Hepatocellular Carcinoma (HCC)
HCC arterialization disrupts hepatic sinusoidal flow and portal hemodynamics.

![Liver Cancer HCC](scenarios/03_liver_cancer_hcc.png)

### 4. Brain Tumor (Glioblastoma)
Glioblastoma neovasculature alters cerebral blood flow and carotid hemodynamics.

![Brain Tumor GBM](scenarios/04_brain_tumor_gbm.png)

### 5. Multi-Site Atherosclerosis
Plaque accumulation at multiple arterial bifurcations with low/oscillatory WSS.

![Multi-Site Atherosclerosis](scenarios/05_multi_atherosclerosis.png)

### 6. Multi-Site Arterial Stenosis
Severe narrowing creates extreme WSS hotspots (>400--1000+ dyne/cm^2).

![Multi-Site Stenosis](scenarios/06_multi_stenosis.png)

### 7. Combined Severe Pathology
Co-existing atherosclerosis, stenosis, and malignancy in a single patient.

![Combined Pathology](scenarios/07_combined_pathology.png)

---

## Wall Shear Stress Data

All WSS values are sourced from peer-reviewed hemodynamic literature:

| Vascular Region | WSS (dyne/cm^2) | Physiological Significance |
|:---|:---:|:---|
| Hepatic sinusoids | 0.1--0.6 | Ultra-low; fenestrated endothelium enables NP access |
| Lymphatic vessels | 0.1--0.6 | Near-stagnant drainage flow |
| Venous circulation | 1--6 | Low-pressure, high-capacitance return |
| Atherosclerotic sites | <4 | Pathological; promotes plaque formation |
| Carotid arteries | 10--20 | Physiological; maintains endothelial homeostasis |
| Arterioles | ~55 | High shear; drives nanoparticle margination |
| General arterial | 10--70 | Pulsatile systemic circulation |
| Tumor vasculature | 0.2--4 | Chaotic; elevated interstitial pressure |
| Stenotic regions | >100--1000+ | Extreme; ruptures soft lipid bilayers |

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

# Generate all scenario figures
python generate_scenarios.py

# Generate a specific scenario
python generate_scenarios.py healthy
python generate_scenarios.py lung_cancer

# Generate the interactive 3D visualization
python generate_viz.py
```

### Available Scenarios

| Key | Scenario | Output |
|:---|:---|:---|
| `healthy` | Healthy Baseline | `scenarios/01_healthy_baseline.png` |
| `lung_cancer` | Lung Cancer | `scenarios/02_lung_cancer.png` |
| `liver_cancer` | Hepatocellular Carcinoma | `scenarios/03_liver_cancer_hcc.png` |
| `brain_tumor` | Brain Tumor (Glioblastoma) | `scenarios/04_brain_tumor_gbm.png` |
| `atherosclerosis` | Multi-Site Atherosclerosis | `scenarios/05_multi_atherosclerosis.png` |
| `stenosis` | Multi-Site Arterial Stenosis | `scenarios/06_multi_stenosis.png` |
| `combined` | Combined Severe Pathology | `scenarios/07_combined_pathology.png` |

---

## How It Works

The entire visualization is **programmatically generated** -- no external mesh files, 3D models, or image assets required.

### 2D Scenario Figures (Matplotlib)

| Component | Method |
|:---|:---|
| Blood vessels | Cubic spline paths with multi-layer glow rendering for 3D depth effect |
| Glow effect | 4 concentric translucent halos (atmosphere, outer, inner, core) + specular highlight |
| Sinusoidal beds | Stochastic scatter point clouds in ellipsoidal volumes |
| Color mapping | Logarithmic scale: `log10(WSS)` mapped to indigo-cyan-green-yellow-orange-red-purple |
| Pathological markers | Diamond (plaque), star (stenosis), square scatter (tumor vasculature) |
| Depth simulation | Veins rendered darker (depth-fading) to appear behind arteries |

### Interactive 3D Visualization (Plotly)

| Component | Method |
|:---|:---|
| Body outline | 14 parametric ellipsoids (torso, head, limbs) at 6% opacity |
| Blood vessels | Tube meshes via Rotation-Minimizing Frames (RMF) around cubic spline paths |
| Export | Plotly HTML with CDN-loaded JavaScript |

---

## Project Structure

```
shear-stress-3d-viz/
├── generate_scenarios.py  # Scenario-based 2D figures (7 scenarios)
├── generate_figure_v2.py  # Base 2D circulatory system figure
├── generate_viz.py        # Interactive 3D Plotly visualization
├── scenarios/             # Generated scenario figures (PNG + PDF)
│   ├── 01_healthy_baseline.png
│   ├── 02_lung_cancer.png
│   ├── 03_liver_cancer_hcc.png
│   ├── 04_brain_tumor_gbm.png
│   ├── 05_multi_atherosclerosis.png
│   ├── 06_multi_stenosis.png
│   └── 07_combined_pathology.png
├── docs/
│   └── index.html         # Interactive 3D visualization (Plotly)
├── requirements.txt       # matplotlib, plotly, numpy, scipy
├── LICENSE                # MIT
└── README.md              # This file
```

---

## Technical Details

### Coordinate System (2D Figures)
- **X**: Left/Right (30--72 cm range)
- **Y**: Inferior/Superior (0--100 cm range)
- **Origin**: Approximate navel position at (50, 42)
- **Units**: Centimeters

### Vessel Rendering Algorithm
Vessels are rendered with a multi-layer glow technique for 3D depth perception:
1. **Cubic spline interpolation** (`scipy.interpolate.splprep/splev`) of anatomical control points
2. **4-layer translucent glow** with decreasing width and increasing opacity
3. **Core vessel** at full opacity with WSS-mapped color
4. **Specular highlight** (thin white center line) simulating light reflection

### Color Scale
The WSS range spans 4 orders of magnitude (0.1--1000+ dyne/cm^2), requiring a logarithmic color mapping:

```
Deep Indigo (0.1) -> Cyan (1) -> Green (3) -> Yellow (10) -> Orange (30) -> Red (100) -> Purple (1000)
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

This project is licensed under the MIT License -- see [LICENSE](LICENSE) for details.

---

<p align="center">
  <i>Developed at the National University of Singapore, Department of Pharmacy and Pharmaceutical Sciences</i>
</p>
