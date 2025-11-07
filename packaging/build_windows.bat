@echo off
REM Build VISUO1.exe using PyInstaller
setlocal enabledelayedexpansion
cd /d %~dp0\..
python -m pip install --upgrade pip
python -m pip install pyinstaller
pyinstaller --clean --noconfirm packaging\visuo1.spec

REM Output will be in dist\VISUO1\VISUO1.exe
pause
