# -*- mode: python ; coding: utf-8 -*-

"""PyInstaller spec file for VISUO1.
Adjust datas / binaries / hiddenimports as needed during testing.
Generate with: pyinstaller --clean --noconfirm packaging/visuo1.spec
"""

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Dynamically gather hidden imports for packages that use plugin discovery
radiomics_hidden = collect_submodules('radiomics')
pyqt_hidden = [
    'PyQt6.QtCore','PyQt6.QtGui','PyQt6.QtWidgets','PyQt6.QtMultimedia','PyQt6.QtMultimediaWidgets'
]
matplotlib_hidden = collect_submodules('matplotlib')

# Data files (icons, etc.) -- add real paths if you have them
_datas = []  # e.g., [('packaging/icon.icns','.'),]

block_cipher = None


a = Analysis(
    ['packaging/run_visuo1.py'],
    pathex=[],
    binaries=[],
    datas=_datas + collect_data_files('radiomics') + collect_data_files('matplotlib'),
    hiddenimports=radiomics_hidden + pyqt_hidden + matplotlib_hidden + ['dtw','SimpleITK','seaborn'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests'],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VISUO1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # no terminal window
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='VISUO1'
)
