# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DCM Tool
# Usage: pyinstaller DCM_Tool.spec

import sys
import os
from pathlib import Path

block_cipher = None

# SPECPATH is set automatically by PyInstaller to the directory that contains
# this .spec file, which is always the project root.
_project_root = SPECPATH

# Explicitly list every submodule so PyInstaller bundles them all.
# collect_submodules() is unreliable for local packages when the working
# directory isn't on sys.path at analysis time.
_hidden = [
    # --- core package ---
    'core',
    'core.dcm_model',
    'core.dcm_parser',
    'core.dcm_writer',
    'core.dcm_compare',
    # --- gui package ---
    'gui',
    'gui.styles',
    'gui.parameter_editor',
    'gui.compare_view',
    'gui.merge_dialog',
    'gui.main_window',
    # --- Qt / matplotlib / numpy ---
    'PyQt5.sip',
    'PyQt5.QtPrintSupport',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'matplotlib',
    'matplotlib.backends.backend_qt5agg',
    'matplotlib.backends.backend_agg',
    'matplotlib.figure',
    'matplotlib.pyplot',
    'numpy',
]

# Guard: locate resources relative to the spec file, not cwd
_datas = []
_res_src = os.path.join(_project_root, 'resources')
if os.path.exists(_res_src):
    _datas.append((_res_src, 'resources'))

a = Analysis(
    [os.path.join(_project_root, 'main.py')],
    pathex=[_project_root],
    binaries=[],
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'email', 'html', 'http', 'xml'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DCM_Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # set to 'resources/icon.ico' if you add one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DCM_Tool',
)
