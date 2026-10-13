# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', '_pytest'],
    noarchive=False,
    optimize=0,
)

# PyInstaller's ctypes scanner can pick up ICU DLLs from unrelated tools on
# the build machine (for example Poppler). Those ICU binaries are incompatible
# with the Qt build shipped by PySide6. Qt's Windows binary package uses the
# Windows ICU implementation, so do not redistribute those accidental copies.
a.binaries = [
    item for item in a.binaries
    if item[0].lower() not in {"icuuc.dll", "icudt78.dll"}
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PC-Builder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PC-Builder',
)
