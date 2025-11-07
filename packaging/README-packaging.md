# Packaging VISUO1 as a Standalone App (macOS & Windows)

This guide outlines how to build platform-specific distributable applications for VISUO1 so end users can run it without installing Python or dependencies manually.

## Overview
We will use **PyInstaller** to create:
- macOS: an `.app` bundle and optionally a signed DMG
- Windows: a standalone directory with `VISUO1.exe` (optionally a single-file exe)

## 1. Ensure Clean Environment
Create a fresh virtual environment with only required packages (avoid dev-only libs):

```
python -m venv build_env
source build_env/bin/activate  # macOS/Linux
# On Windows: build_env\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

## 2. Entry Point
The app launches from `app/main.py` which constructs the GUI. We'll create a tiny wrapper script `run_visuo1.py` for PyInstaller to keep paths predictable.

## 3. PyInstaller Spec (Recommended)
A custom spec file allows fine control over hidden imports (e.g., for PyQt6, dtw, radiomics, SimpleITK, matplotlib backends).

Create `visuo1.spec` (example stub included in this folder when generated). Adjust `datas` for any non-Python assets (icons, templates, example data).

### Common Hidden Imports
Add if PyInstaller warns:
- `PyQt6.QtCore`, `PyQt6.QtGui`, `PyQt6.QtWidgets`, `PyQt6.QtMultimedia`, `PyQt6.QtMultimediaWidgets`
- `radiomics.featureextractor` and its plugin modules
- `SimpleITK`
- `dtw`
- `matplotlib`, `seaborn`

## 4. Running PyInstaller

Command (macOS example):
```
pyinstaller --clean --noconfirm visuo1.spec
```
If using just CLI args:
```
pyinstaller --name VISUO1 \
  --windowed --onefile \
  --icon=packaging/icon.icns \
  run_visuo1.py
```
Windows icon: use `.ico` instead of `.icns`.

## 5. Testing the Build
Locate output in `dist/`.
- macOS: `VISUO1.app` (double-click)
- Windows: `VISUO1.exe`
Run and verify: image loading, processing, ranking/heatmaps, ROI persistence.

## 6. Adding Data Files
If runtime needs sample templates or default config:
Add to spec `datas=[('path/to/template.png','templates'), ...]`.
Access via relative path to `sys._MEIPASS` (PyInstaller temp extraction folder) when bundled. Example helper:
```python
import sys, os
BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
RESOURCE_PATH = os.path.join(BASE_DIR, 'templates', 'template.png')
```

## 7. Code Adjustments for Bundling
- Replace any absolute dev paths with dynamic base lookups.
- Avoid writing outside user-writable locations (use `~/.visuo1` or a chosen output dir).
- Ensure single-instance lock works when executable path changes (lock name stays stable).

## 8. macOS Signing & Notarization (Optional)
For distribution beyond local:
1. Create developer certs.
2. Codesign:
```
codesign --deep --force --verify --verbose --sign "Developer ID Application: Your Name" dist/VISUO1.app
```
3. Notarize using `xcrun altool` or `notarytool`.
4. Staple:
```
xcrun stapler staple dist/VISUO1.app
```

## 9. Windows Installer (Optional)
Use tools like Inno Setup or NSIS to wrap the `dist/` folder into an installer wizard.

## 10. Updates Strategy
For future updates, increment a version constant (e.g., in `app/main.py`) and rebuild. Consider auto-update frameworks only once stability is reached.

## 11. Troubleshooting
- Missing Qt plugins: add `--add-binary` for platform plugins (PyInstaller usually picks these up).
- Large size: avoid `--onefile` if startup time increases; prune heavy unused packages.
- SimpleITK size: It's large; if not required for basic workflows, make its features optional.

## 12. Next Steps
Automate builds with a GitHub Action matrix (macOS + Windows) using `pyinstaller` in each job and upload artifacts.

---
This folder will also contain the spec file and the wrapper script once added.
