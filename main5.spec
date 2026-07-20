# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main5.py'],
    pathex=[],
    binaries=[],
    datas=[('audio.mp3', '.'), ('audio1.mp3', '.'), ('Loading Screen.mp3', '.'), ('favicon.ico', '.'), ('Loading_icon.gif', '.'), ('hl.json', '.'), ('recording.json', '.'), ('recording111.json', '.')],
    hiddenimports=['PyQt6.QtMultimedia', 'serial', 'numpy', 'matplotlib', 'matplotlib.backends.backend_qtagg'],
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
    name='main5',
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
    icon='favicon.ico',
)
