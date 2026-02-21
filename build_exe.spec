# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# 收集 mediapipe 的所有文件（包括 C 绑定、模型等）
mp_datas, mp_binaries, mp_hiddenimports = collect_all('mediapipe')

# 收集 opencv 的所有文件
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
    bootloader_ign
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
