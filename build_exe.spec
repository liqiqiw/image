# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

mp_datas, mp_binaries, mp_hiddenimports = collect_all('mediapipe')
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all('cv2')

a = Analysis(
    ['crop_portrait_gui.py'],
    pathex=[],
    binaries=mp_binaries + cv2_binaries,
    datas=[
        ('pose_landmarker.task', '.'),
        ('crop_worker.py', '.'),
    ] + mp_datas + cv2_datas,
    hiddenimports=[
        'crop_worker',
        'PIL._tkinter_finder',
        'numpy',
    ] + mp_hiddenimports + cv2_hiddenimports + collect_submodules('mediapipe'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='autoCut',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
