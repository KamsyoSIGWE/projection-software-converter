# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

project_root = Path.cwd()
src_dir = project_root / "src"
icon_path = project_root / "assets" / "app.ico"
version_info_path = project_root / "packaging" / "version_info.txt"
is_windows = sys.platform.startswith("win")

datas = collect_data_files("projection_software_converter")

a = Analysis(
    ["src/projection_software_converter/__main__.py"],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ProjectionSoftwareConverter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(icon_path) if is_windows and icon_path.exists() else None,
    version=str(version_info_path) if is_windows and version_info_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Projection Software Converter",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Projection Software Converter.app",
        icon=None,
        bundle_identifier="com.projectionsoftwareconverter.app",
    )
