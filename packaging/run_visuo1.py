# packaging/run_visuo1.py
"""Wrapper entry point for PyInstaller builds.

This script adjusts resource lookup to support bundled execution and then
launches the main application.
"""
import os, sys
from pathlib import Path

# Ensure we can import app modules regardless of PyInstaller _MEIPASS
BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
APP_DIR = BASE_DIR / 'app'
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Optional: set a stable working directory for relative outputs
os.chdir(str(BASE_DIR))

from app.main import main as app_main  # type: ignore

if __name__ == '__main__':
    app_main()
