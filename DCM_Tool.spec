# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DCM Tool
# Usage: pyinstaller DCM_Tool.spec
#
# All application modules (dcm_*.py, ui_*.py) live at the project root so
# PyInstaller finds them automatically via normal import tracing from main.py.
# No hiddenimports tricks needed for local code.

import os

block_cipher = None

_datas = []
_res = os.path.join(SPECPATH, 'resources')
if os.path.exists(_res):
    _datas.append((_res, 'resources'))

a = Analysis(
    [os.path.join(SPECPATH, 'main.py')],
    pathex=[SPECPATH],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'PyQt5.sip',
        'PyQt5.QtPrintSupport',
        'matplotlib.backends.backend_qt5agg',
        'matplotlib.backends.backend_agg',
        'numpy',
    ],
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
