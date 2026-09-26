# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MUSTACOM BUSINESS MANAGER.

Produces an *onedir* bundle (fast startup, standard for Inno Setup):
    dist/mustacom/MUSTACOM-Business-Manager.exe   (Windows)
    dist/mustacom/mustacom-business-manager       (Linux validation build)

The Inno Setup script (installer/mustacom.iss) ships the whole dist/mustacom
folder; the GitHub Actions workflow uploads the resulting installer.

Used by build/build_windows.ps1, .github/workflows/windows-installer.yml and
the local Linux validation build (build/build_linux_check.sh).
"""

import os
from pathlib import Path

import barcode
from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent

block_cipher = None

# runtime data that must travel inside the bundle
extra_datas = [
    # SQLite migrations, loaded relative to mustacom/db/__init__ at runtime
    (str(ROOT / "mustacom" / "db" / "migrations"), os.path.join("mustacom", "db", "migrations")),
    # python-barcode ships its label font outside of the python modules
    (os.path.join(os.path.dirname(barcode.__file__), "fonts"), os.path.join("barcode", "fonts")),
]
extra_datas += collect_data_files("qrcode")

a = Analysis(
    [str(ROOT / "build" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=extra_datas,
    hiddenimports=[
        "PySide6.QtPrintSupport",
        "PySide6.QtSvg",
        "openpyxl",
        "qrcode",
        "barcode",
        "barcode.writer",
        "barcode.codex",
        "barcode.ean",
        "barcode.qrcode",
        "PIL",
        "PIL._imagingft",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "sphinx"],
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
    name="MUSTACOM-Business-Manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,               # pure GUI app; use --console for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / ("mustacom.ico" if os.name == "nt" else "logo.png")),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="mustacom",
)
