# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

root = os.path.abspath(SPECPATH)
qt_bin = os.path.join(root, ".buildenv", "Lib", "site-packages", "PyQt6", "Qt6", "bin")

datas = [(os.path.join(root, "icon.ico"), ".")]
binaries = [
    (os.path.join(root, "yt_dlp.exe"), "."),
    (os.path.join(qt_bin, "concrt140.dll"), "PyQt6/Qt6/bin"),
    (os.path.join(qt_bin, "msvcp140_atomic_wait.dll"), "PyQt6/Qt6/bin"),
    (os.path.join(qt_bin, "msvcp140_codecvt_ids.dll"), "PyQt6/Qt6/bin"),
    (os.path.join(qt_bin, "vccorlib140.dll"), "PyQt6/Qt6/bin"),
    (os.path.join(qt_bin, "vcruntime140_threads.dll"), "PyQt6/Qt6/bin"),
]
hiddenimports = []
qtawesome = collect_all("qtawesome")
datas += qtawesome[0]
binaries += qtawesome[1]
hiddenimports += qtawesome[2]

a = Analysis(
    [os.path.join(root, "ytdl.py")],
    pathex=[], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)

# Qt uses the Windows system ICU. Host Poppler ICU binaries are incompatible.
a.binaries = [entry for entry in a.binaries
              if not (entry[0].lower().startswith("icu") and entry[0].lower().endswith(".dll"))]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name="ytdl", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True, upx_exclude=[],
    runtime_tmpdir=None, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None,
    entitlements_file=None, icon=[os.path.join(root, "icon.ico")],
)
