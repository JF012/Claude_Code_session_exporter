# -*- mode: python ; coding: utf-8 -*-
# Empaqueta la v4 como un único .exe autónomo (sin consola).
# Uso:  pyinstaller ClaudeSessionExporter_v4.spec

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('exporter_icon.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ClaudeSessionExporter',
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
    icon=['exporter_icon.ico'],
)
