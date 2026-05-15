# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DCM Tool
# Usage: pyinstaller DCM_Tool.spec

import sys
import os

block_cipher = None

# SPECPATH is the directory containing this .spec file (= project root).
# Insert it into sys.path NOW so that Analysis and collect_submodules can
# actually find the local 'gui' and 'core' packages during analysis.
sys.path.insert(0, SPECPATH)

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect every module inside the two local packages automatically
_hidden = (
    collect_submodules('gui') +
    collect_submodules('core') +
    [
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
)

_datas = []
_res_src = os.path.join(SPECPATH, 'resources')
if os.path.exists(_res_src):
    _datas.append((_res_src, 'resources'))

a = Analysis(
    [os.path.join(SPECPATH, 'main.py')],
    pathex=[SPECPATH],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
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
