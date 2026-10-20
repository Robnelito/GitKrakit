# -*- mode: python ; coding: utf-8 -*-
"""Portable one-file Windows build consumed by ``pyupdater build``."""

from pathlib import Path

import pyupdater


PROJECT_ROOT = Path.cwd()
PYUPDATER_HOOKS = Path(pyupdater.__file__).resolve().parent / "hooks"

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[(str(PROJECT_ROOT / "gitkrakit" / "resources" / "fonts"), "gitkrakit/resources/fonts")],
    hiddenimports=["pyupdater.client"],
    hookspath=[str(PYUPDATER_HOOKS)],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# PyUpdater expects the platform-specific temporary name (win.exe). It renames
# the binary to GitKrakit.exe inside the update archive after PyInstaller runs.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="win",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
