<!-- ORIGINAL (LEGACY) INTRO SECTION BELOW PRESERVED -->
# VISUO1: A Platform for SWIR Time-Series Image Analysis

VISUO1 is a powerful and comprehensive desktop application built with Python and PyQt6, designed to automate the entire workflow for analyzing time-series data from preclinical short-wave infrared (SWIR) imaging studies.

The application intelligently handles everything from initial file discovery and image registration to advanced statistical analysis and data visualization, ensuring consistency, reproducibility, and the discovery of meaningful biological insights from complex imaging datasets.

## Application Preview

VISUO1 Application
<img width="1728" height="1117" alt="Screenshot 2025-11-07 at 11 40 18 AM" src="https://github.com/user-attachments/assets/f05ac583-2a6f-4fc6-8797-d84fc52c0d3e" />

## ✨ Core Features

*   **Automated File Discovery:** Scans directories to automatically parse and group time-series image pairs based on filename metadata.
*   **Live Interactive Preview:** A real-time preview panel for configuring all processing parameters (overlay, intensity, LUT) before batch processing.
*   **Advanced Registration:**
  *   **Universal Template-Based:** Aligns the entire dataset to a common reference template for inter-animal consistency.
  *   **Intra-Animal Time-Series:** Aligns all frames for a single animal to its first time point to correct for movement over long sessions.
*   **Quantitative Feature Extraction:** Utilizes the powerful `pyradiomics` library to extract a wide range of quantitative features (First Order, GLCM, GLSZM) from defined signal regions.
*   **Spatiotemporal Signal Path Analysis:** Generates advanced visualizations to track signal dynamics over time, including:
  *   **Animated GIFs:** Creates a dynamic movie of the signal progression for each animal, complete with a time-progression bar.
  *   **Time-Coded Contour & Phase Maps:** Visualizes the signal's spatial boundaries and persistence over time, overlaid on the animal's anatomy.
*   **Sophisticated Data Analysis:**
  *   **Feature Ranking:** Employs statistical models (DTW, LME) to rank features based on unsupervised clustering or specific scientific hypotheses.
  *   **Heatmap Clustering:** Generates univariate and multivariate heatmaps to visualize similarities between experimental groups based on their time-series profiles.
*   **Reproducibility:** Save and load the entire application state, including all UI settings and file paths, to a JSON file for perfectly reproducible analysis.

##  Workflow Overview

The application is organized into two main stages: Processing and Analysis.

### 1. Image Processing Pipeline
This stage transforms raw, inconsistently positioned images into standardized, quantitative data and visualizations.

![20250716_G11-M-12Gy-SHOV-A02_animation](https://github.com/user-attachments/assets/810d940a-a7d1-43ae-9123-68608a4b643d)  ![20250711_G07-F-00Gy-DIZE-A03_animation](https://github.com/user-attachments/assets/868445ef-c2f8-4ffe-ba61-c5951fe8f0e8)

*   **Data Input:** The user selects a main data directory and an output directory. The app automatically finds and groups all `_WF_` (widefield) and `_FL_` (fluorescence) image pairs.
*   **Configuration:** Using the live preview, the user configures global settings like intensity normalization, LUT colormaps, registration templates, and the final cropping ROI.
*   **Batch Processing:** In a background thread, the app processes every animal to generate:
  *   Individual and Master Time-Series Collages.
  *   Animated GIFs with a time-progression bar.
  *   Advanced Signal Path Analysis maps (Contour, Phase).
  *   Two primary data files:
    *   `_Raw_Results.csv`: Contains every calculated feature for each animal at every time point.
    *   `_Group_Summary.csv`: Contains aggregated statistics (mean, median, std) for each experimental group.

![G05-F-12Gy-DIZE_MASTER_COLLAGE](https://github.com/user-attachments/assets/16660de4-378b-48ff-93b5-498396065dc9)

### 2. Data Analysis Pipeline
This stage provides tools to interpret the data generated during processing.

*   **Feature Ranking:** Load the `_Raw_Results.csv` to identify the most significant features using three methods:
  *   **Overall Ranking (Unsupervised):** Finds features that best separate groups based on Dynamic Time Warping (DTW) distance.
  *   **Interaction Effect (Hypothesis-Driven):** Uses a Linear Mixed-Effects model to test for interactions between factors (e.g., Time & Dose).
  *   **Normalization Effect (Hypothesis-Driven):** Ranks features on their ability to show a return-to-baseline effect for a treated group.
*   **Heatmap Clustering:** Load the `_Group_Summary.csv` to generate clustered heatmaps that visualize the similarity between experimental groups, either for a single feature or averaged across all features.
<img width="4156" height="4294" alt="multivariate_clustered_heatmap" src="https://github.com/user-attachments/assets/41a27b4a-0683-4984-a179-1530aea7cc0b" />

## 🔧 Technology Stack

*   **GUI Framework:** PyQt6
*   **Core Numerical & Array Operations:** NumPy
*   **Image Processing & Analysis:** OpenCV, Scikit-image, Tifffile
*   **Statistical Feature Extraction:** Pyradiomics
*   **Data Handling & Analysis:** Pandas, Statsmodels
*   **Plotting & Visualization:** Matplotlib, Seaborn
*   **Animation:** Imageio

## 🚀 Getting Started

### Prerequisites

*   Python 3.8 or newer
*   An environment manager like `venv` or `conda` is recommended.

### Installation & Running

1.  **Clone the repository:**
  ```bash
  git clone https://github.com/your-username/VISUO1.git
  cd VISUO1
  ```

2.  **Create a virtual environment (recommended):**
  ```bash
  python -m venv venv
  source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
  ```

3.  **Install the required dependencies:**
  ```bash
  pip install -r requirements.txt
  ```

4.  **Run the application:**
  ```bash
  python main.py
  ```

## 📁 Project Architecture

The project uses a modular architecture that separates the user interface from the backend processing logic.

<!-- END OF ORIGINAL SECTION -->

---
## APPENDIX A: Extended Architecture & Packaging (New)

> The following appendix augments the original README with deeper architectural details, module‑level responsibilities, data/analysis pipelines, and full standalone packaging guidance for macOS and Windows.

### A.1 High-Level Capabilities (Consolidated)
| Area | Highlights |
|------|------------|
| File Discovery | Regex-driven grouping of WF/FL pairs. |
| Preview & ROI | Multi-ROI overlay, composite operations, adaptive mapping on zoom/pan. |
| Registration | Intra-series alignment + optional template centering utility. |
| Radiomics | Pyradiomics feature classes; optional lightweight legacy fallback. |
| Spatiotemporal | Contour evolution, phase map, temporal color progression GIFs. |
| Analytics | DTW ranking, mixed-effects hypotheses, clustering heatmaps. |
| Packaging | PyInstaller spec + wrapper for turnkey distribution. |

### A.2 Detailed Directory Map
```
app/
  main.py                 # Entry + single-instance guard
  gui/
  main_window.py        # Orchestrates panels, threads, processing lifecycle
  preview_panel.py       # Zoomable image view, overlays, timestamp, multi-ROI
  settings_panel.py      # Visualization, intensity window, registration toggles
  analysis_panel.py      # Ranking + heatmap triggers and exports
  feature_selection_panel.py # Radiomics feature selection UI
  interactive_roi.py     # Crop ROI widget with handles
  multi_roi_overlay.py   # Multi-shape ROI editing + composite logic
  roi_manager.py         # ROI data model & serialization
  outline_overlay.py     # Passive outline overlay (currently disabled in settings)
  worker.py              # Threaded processing pipeline implementation
  splash_screen.py       # Optional video splash
  processing/
  file_handler.py        # Filename parsing & grouping utilities
  image_processor.py     # LUT, overlay, cropping, gradients, animations
  registration.py        # Template centering helper
  signal_path_analysis.py# Contour/phase/time maps & ECC registration
  feature_extraction.py  # Pyradiomics feature extraction wrapper
  _feature_extraction.py # Legacy simple feature set
  timeseries_analysis.py # DTW ranking, mixed-effects, summarization
  heatmap_generator.py   # DTW distance matrices + clustering
packaging/
  run_visuo1.py            # PyInstaller wrapper
  visuo1.spec              # Build spec (hiddenimports, datas)
  build_macos.sh           # macOS build script
  build_windows.bat        # Windows build script
```

### A.3 Processing Pipeline Contracts
| Stage | Input | Output | Notes |
|-------|-------|--------|-------|
| Discovery | Folder of TIFFs | grouped dict | Robust to extra tokens. |
| Registration (optional) | WF/FL frames | aligned frames | ECC or template shift. |
| Crop & Overlay | Aligned frames + ROI | Composite RGB frames | Intensity window + LUT applied. |
| Feature Extraction | Cropped or full region | Feature rows | Pyradiomics per time point. |
| Signal Path | FL frames | Contours, phase maps | Otsu + boost segmentation. |
| Aggregation | Feature rows | Raw + Group CSVs | Group stats (mean/median/std). |
| Analytics | CSVs | Rankings, heatmaps | DTW + mixed effects modeling. |

### A.4 Ranking Algorithms Summary
| Algorithm | Core Metric | Strength |
|-----------|------------|----------|
| DTW Separation | Distance dispersion between group curves | Captures temporal shape differences |
| Mixed Effects Interaction | p-value / effect size | Tests factor interplay (e.g., Dose×Time) |
| Normalization Effect | Deviation return score | Highlights recovery-to-baseline patterns |

### A.5 Packaging Quick Reference
| Task | Command (macOS) | Command (Windows) |
|------|-----------------|-------------------|
| Prep venv | `python -m venv build_env; source build_env/bin/activate` | `python -m venv build_env && build_env\Scripts\activate` |
| Install deps | `pip install -r requirements.txt pyinstaller` | Same |
| Build | `pyinstaller --clean --noconfirm packaging/visuo1.spec` | Same with backslashes |
| Run Result | `open dist/VISUO1/VISUO1` | `dist\VISUO1\VISUO1.exe` |

### A.6 Resource Handling in Bundles
Use:
```python
BASE_DIR = getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)
```
Add `datas` entries in spec for icons, templates, defaults.

### A.7 Troubleshooting (Extended)
| Symptom | Likely Cause | Resolution |
|---------|-------------|------------|
| Missing SimpleITK at runtime | Hidden import omitted | Add to spec hiddenimports (already present). |
| Blank heatmap figure | No matching aggregation columns | Verify `_Group_Summary.csv` and chosen suffix. |
| Ranking empty list | Non-numeric feature cols | Ensure coercion; inspect CSV head. |
| ROI composite fails | <2 valid sources | Validate selected component ROI IDs. |

### A.8 Future Enhancements
- Pluggable feature extraction adapters (e.g., deep embeddings).  
- GPU-accelerated DTW / contour extraction.  
- Incremental processing resume.  
- Auto-update & crash reporting channel.  

### A.9 Glossary
| Term | Definition |
|------|------------|
| WF | Widefield grayscale image channel. |
| FL | Fluorescence intensity image channel. |
| ROI | Region of Interest (rect/ellipse/contour/text). |
| DTW | Dynamic Time Warping distance between temporal sequences. |

---
## APPENDIX B: Original + Extended Quick Build Recap
```bash
# macOS (source)
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app/main.py

# macOS (package)
./packaging/build_macos.sh

# Windows (source)
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python app\main.py

# Windows (package)
packaging\build_windows.bat
```

---
_Appendices added without altering original descriptive content._

## License

VISUO1 is distributed under the VISUO1 Non‑Commercial Research License (NCRL) v1.0. See `LICENSE` for the full terms and `LICENSE-POLICY.md` for a plain‑language summary. For commercial licensing inquiries, please open an issue in this repository to contact the maintainers.

---
## Table of Contents
1. Overview & Core Capabilities  
2. End‑to‑End Workflow  
3. Directory Structure  
4. Key Modules & Responsibilities  
5. Data Flow & Processing Pipeline  
6. Analysis & Ranking Pipeline  
7. Generated Output Files  
8. Building & Running (Source)  
9. Packaging as Standalone Apps (macOS & Windows)  
10. Resource Access in Bundled Mode  
11. Troubleshooting & FAQ  
12. Release & Versioning Considerations  
13. Contributing / Extending  
14. License (Placeholder)  

---
## 1. Overview & Core Capabilities

| Area | Highlights |
|------|------------|
| File Discovery | Automatic grouping of WF/FL TIFF pairs by regex parsing of metadata tokens (date, animal, time, modality). |
| Interactive Preview | Zoom/pan, color LUT windowing, live colorbar, ROI drawing & multi‑ROI set management, overlay timestamp. |
| Registration | Optional intra‑animal time series alignment; optional template centering utility for consistent framing. |
| Feature Extraction | Pyradiomics feature classes (First Order, GLCM, GLSZM) with robust normalization; legacy lightweight extraction fallback. |
| Spatiotemporal Analysis | Contour evolution, phase maps, temporal color progression and animated GIF assembly. |
| Composite Overlays | Dynamic LUT mapping + blending of WF & FL; adaptive ROI remapping on zoom/pan; multi‑ROI union/xor/subtract operations. |
| Ranking & Hypothesis Testing | DTW separation, permutation support, mixed‑effects modeling for interaction/normalization hypotheses. |
| Clustering & Heatmaps | Univariate and aggregated multivariate DTW distance matrices, hierarchical clustering, seaborn heatmaps. |
| Reproducibility | Persist full UI/session state (settings + ROI definitions) to JSON; deterministic file parsing order. |
| Standalone Distribution | Turnkey executables / app bundles via PyInstaller (spec + wrapper provided). |

---
## 2. End‑to‑End Workflow
1. Select input root directory containing TIFF files.  
2. App parses filenames; groups WF/FL pairs by animal/time.  
3. Configure visualization (intensity window, LUT, transparency) & define cropping ROI in preview.  
4. Optionally enable registration/template centering.  
5. Run batch processing (background thread): collage, animation, radiomics features, signal path maps, summary CSVs.  
6. Load Raw Results (`*_Raw_Results.csv`) for feature ranking or Group Summary (`*_Group_Summary.csv`) for clustering/heatmaps.  
7. Export derived plots, ranked tables, cluster heatmaps for downstream interpretation.  

---
## 3. Directory Structure (Key Paths)
```
VISUO1/
  app/
    main.py                # Application entry & single-instance lock
    gui/                   # All PyQt6 widgets & overlays
      main_window.py       # Orchestrates UI + threads
      preview_panel.py     # Image viewer, zoom, timestamp, multi-ROI overlay
      settings_panel.py    # Processing & visualization controls
      analysis_panel.py    # Ranking & heatmap actions
      feature_selection_panel.py  # Radiomics feature class selection
      interactive_roi.py   # Crop ROI widget
      multi_roi_overlay.py # Multi-shape ROI overlay & editing
      outline_overlay.py   # (Passive) anatomical outline overlay
      roi_manager.py       # ROI data model & serialization
      worker.py            # Heavy processing worker (QThread target)
      splash_screen.py     # Optional startup video
    processing/
      file_handler.py      # Filename parsing & grouping utilities
      image_processor.py   # Core imaging primitives & LUT/overlay functions
      registration.py      # Template centering helper
      signal_path_analysis.py # Contour/phase/time map generation
      feature_extraction.py    # Pyradiomics feature extraction
      _feature_extraction.py   # Legacy lightweight extraction
      timeseries_analysis.py   # DTW ranking, mixed-effects, summarization
      heatmap_generator.py     # DTW matrices & clustered heatmaps
  packaging/
    run_visuo1.py          # PyInstaller wrapper entrypoint
    visuo1.spec            # Spec file for deterministic builds
    build_macos.sh         # macOS build helper
    build_windows.bat      # Windows build helper
    README-packaging.md    # Focused packaging/how-to document
  requirements.txt
  README.md (this file)
```

---
## 4. Key Modules & Responsibilities

### `app/main.py`
Single-instance lock, splash screen coordination, constructs `MainWindow`, enters Qt event loop. Provides `main()` for packaging wrapper.

### GUI Layer (`app/gui/`) Highlights
| File | Purpose |
|------|---------|
| main_window.py | Central mediator: loads data, starts workers, binds signals to panels. |
| preview_panel.py | Zoomable view, ROI crop, multi-ROI editing, timestamp & registration overlays. |
| settings_panel.py | Intensity/LUT, registration enable, cropping, watermark, overlay algorithm config. |
| analysis_panel.py | Feature ranking triggers, heatmap generation, export utilities. |
| feature_selection_panel.py | Radiomics feature class and region selection; re-extract triggers. |
| interactive_roi.py | Draggable/resizable rectangular crop ROI. |
| multi_roi_overlay.py | Arbitrary ROI shapes (rect, ellipse, contour, text, composite ops). |
| roi_manager.py | Add/remove/rename/list ROI objects; serialization to JSON. |
| worker.py | Background batch pipeline (collage, features, summaries, signal path). |
| splash_screen.py | Optional non-blocking video while main loads. |

### Processing Layer (`app/processing/`)
- `file_handler.py`: Regex parsing, grouping, random selection.  
- `image_processor.py`: LUT mapping, overlays, cropping, animations, gradient/colorbar generation, outline computation.  
- `registration.py`: Template-centric translation alignment.  
- `signal_path_analysis.py`: ECC registration, threshold segmentation, contour evolution & phase map rendering.  
- `feature_extraction.py`: Clean pyradiomics invocation (per-call extractor).  
- `_feature_extraction.py`: Lightweight manual feature set (intensity/shape/GLCM).  
- `timeseries_analysis.py`: Data cleaning, DTW-based ranking, mixed-effects testing, group curve summarization.  
- `heatmap_generator.py`: Summary curve parsing, distance matrix construction, hierarchical clustering & plotting.

---
## 5. Data Flow & Processing Pipeline
1. Parse filenames → structured grouping: `{ANIMAL_KEY -> TIME_POINT -> {WF, FL}}`.  
2. For each animal & time point: load frames; optionally register (intra-series or template).  
3. Apply cropping ROI & intensity/LUT; build composite overlay frames.  
4. Extract features (radiomics) per time point region (crop or entire image or specific ROI).  
5. Signal path analysis (threshold/Otsu segmentation, contour metrics).  
6. Aggregate per-animal & per-group statistics → write `_Raw_Results.csv` & `_Group_Summary.csv`.  
7. Generate visual outputs: collages, GIF animations, phase/contour maps.  

Performance considerations: heavy loops run inside `Worker` QThread; periodic progress/status signals keep GUI responsive.

---
## 6. Analysis & Ranking Pipeline
### Feature Ranking Methods
| Method | Description |
|--------|-------------|
| DTW Separation | Compute DTW distances between group curves per feature; rank by inter-group separation metrics. |
| Interaction (Mixed Effects) | Linear Mixed-Effects modeling for factor interactions (e.g., Time × Dose). |
| Normalization Effect | Score features by pattern consistent with treatment normalization to baseline. |

### Heatmap Clustering
1. Build per-group summary curves (median or mean).  
2. Calculate univariate DTW distance matrices (one per feature) or aggregate multivariate matrix (average minmax-scaled per-feature distances).  
3. Perform hierarchical clustering; render seaborn heatmap with dendrogram ordering; export image.  

---
## 7. Generated Output Files
| File | Contents |
|------|----------|
| `*_Raw_Results.csv` | Row per animal per time point; all extracted features + metadata. |
| `*_Group_Summary.csv` | Aggregated stats (mean/median/std) per group per time point + derived columns. |
| Collage PNGs | Individual & master collages of frames (overlay + colorbar). |
| Animation GIFs | Temporal progression with progress/time bar. |
| Phase / Contour Maps | Static visualizations of spatial activation dynamics. |
| Rankings CSV (optional) | Exported sorted feature importance metrics. |
| Heatmap PNGs | Clustered group similarity visualizations. |
| Session JSON (future) | Persisted state for reproducibility (settings + ROI). |

---
## 8. Building & Running From Source
### Prerequisites
- Python ≥ 3.9 (radiomics & SimpleITK compatibility).  
- System libs for PyQt6 (installed via pip).  

### Steps
```bash
git clone https://github.com/ShayanShafiee/VISUO1.git
cd VISUO1
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app/main.py  # or python -m app.main
```

Optional debug (show console): run with `python app/main.py --debug` (future flag placeholder).

---
## 9. Packaging as Standalone Apps (macOS & Windows)
PyInstaller configuration is provided in `packaging/`.

### Wrapper Entry Point
`packaging/run_visuo1.py` imports `app.main.main()` while adjusting `sys.path` for bundled execution.

### Spec File
`packaging/visuo1.spec` includes hidden imports for:
- PyQt6 (Core, Gui, Widgets, Multimedia, MultimediaWidgets)
- radiomics & matplotlib plugin modules
- SimpleITK, seaborn, dtw

### macOS Build
```bash
cd VISUO1
python -m venv build_env
source build_env/bin/activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --clean --noconfirm packaging/visuo1.spec
open dist/VISUO1/VISUO1  # run app
```
Produces an onedir bundle. For .app wrapping/codesigning you can treat `dist/VISUO1` as contents; or adjust spec to emit `.app` directly.

### Windows Build
```bat
cd VISUO1
python -m venv build_env
build_env\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --clean --noconfirm packaging\visuo1.spec
dist\VISUO1\VISUO1.exe
```

### Onefile Variant (Optional)
Add `--onefile` to the PyInstaller CLI or modify spec to produce a single executable (slower startup, large unpack step). Example:
```bash
pyinstaller --name VISUO1 --windowed --onefile packaging/run_visuo1.py
```

### Code Signing & Notarization (macOS Optional)
```bash
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: Your Name" dist/VISUO1/VISUO1
xcrun notarytool submit dist/VISUO1/VISUO1.zip --apple-id <id> --team-id <team> --password <app-password>
xcrun stapler staple dist/VISUO1/VISUO1
```

### Windows Installer (Optional)
Use Inno Setup / NSIS to wrap `dist/VISUO1` folder. Script tasks: add icon, create Start Menu shortcut, add uninstall entry.

### Updating / Versioning
Increment a version constant (add to `app/main.py` or a dedicated `__version__.py`). Rebuild with PyInstaller; distribute new artifact.

---
## 10. Resource Access in Bundled Mode
When bundled via PyInstaller, temporary extraction base is at `sys._MEIPASS`. Use a helper:
```python
import sys, os
BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
ICON_PATH = os.path.join(BASE_DIR, 'resources', 'icon.png')
```
Add resources through `datas=[('resources/icon.png','resources')]` in spec.

---
## 11. Troubleshooting & FAQ
| Issue | Cause | Fix |
|-------|-------|-----|
| Missing Qt plugin | PyInstaller didn’t collect platform plugins | Add `--add-binary` for `PyQt6/Qt6/plugins` or rely on spec auto collection. |
| Slow startup (onefile) | Large libs (SimpleITK, radiomics) decompress | Prefer onedir; or prune unused packages. |
| Feature columns non-numeric | CSV type parsing mismatch | Coerce with `pd.to_numeric(errors='coerce')` before ranking (already handled). |
| ROI drift after zoom | Out-of-sync transform mapping | Preview panel overlay sync timer re-applies canonical image-space ROI (built-in). |
| Large executable size | Included heavy dependencies | Make radiomics optional; rebuild without SimpleITK if not required. |
| macOS Gatekeeper block | Unsigned app | Perform codesign & notarization as described. |

---
## 12. Release & Automation (Future)
Add a GitHub Actions matrix workflow: macOS + Windows runners executing PyInstaller; upload artifacts to Releases. Example steps:
1. Checkout & setup Python.  
2. Install dependencies + PyInstaller.  
3. Run spec; store `dist/` artifact.  
4. (macOS) Optional codesigning if secrets provided.  

---
## 13. Contributing / Extending
1. Fork & create feature branch.  
2. Add/modify processing module or GUI panel.  
3. Ensure docstring + top path comment style (`# gui/<file>.py`).  
4. Run local processing with sample dataset; verify output integrity.  
5. Submit PR with clear description + before/after examples.  

### Ideas
- Add GPU acceleration for LUT + registration (OpenCL / CUDA via CuPy).  
- Integrate auto-update mechanism.  
- Add plugin architecture for new feature extraction strategies.  

---
## 14. License
License information pending (add SPDX identifier when chosen). For now, treat as All Rights Reserved unless a permissive license is declared.

---
## Quick Start (Standalone Build Recap)
```bash
# macOS
./packaging/build_macos.sh
open dist/VISUO1/VISUO1

# Windows
packaging\build_windows.bat
dist\VISUO1\VISUO1.exe
```

---
## Contact & Support
Open an issue with logs (if runtime) + example filenames to reproduce. Include OS, Python version (for source runs), and steps taken.

---
_This README consolidates architecture, function roles, and distribution methods for VISUO1._
