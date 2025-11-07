#!/usr/bin/env bash
set -euo pipefail
# Build VISUO1 .app bundle using PyInstaller
cd "$(dirname "$0")/.."
python -m pip install --upgrade pip
python -m pip install pyinstaller
pyinstaller --clean --noconfirm packaging/visuo1.spec

# Output will be in dist/VISUO1 (onedir). For a .app bundle wrapper, you can later wrap or codesign.
# To run locally:
# open dist/VISUO1/VISUO1
