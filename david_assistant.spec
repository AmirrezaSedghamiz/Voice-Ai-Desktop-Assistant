# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Specification for David - Local Windows AI Voice Assistant.
Produces a clean Windows x64 release folder (onedir mode) with full native DLLs,
Qt UI runtime, offline Vosk keyword detector, and audio engines.
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None
project_root = Path.cwd()

# Collect hidden imports for dynamic modules
hidden_imports = [
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'vosk',
    'sounddevice',
    'faster_whisper',
    'ctranslate2',
    'piper',
    'onnxruntime',
    'pydantic',
    'psutil',
    'sqlite3',
    'requests',
    'urllib.request',
]
hidden_imports += collect_submodules('src')
hidden_imports += collect_submodules('faster_whisper')
hidden_imports += collect_submodules('vosk')

# Collect data files and native DLLs
datas = [
    (str(project_root / 'assets'), 'assets'),
]
datas += collect_data_files('vosk')
datas += collect_data_files('faster_whisper')

# Binaries: Collect native DLLs from packages if needed
binaries = []
binaries += collect_dynamic_libs('vosk')
binaries += collect_dynamic_libs('sounddevice')
binaries += collect_dynamic_libs('ctranslate2')

a = Analysis(
    ['run_gui.py'],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'notebook', 'IPython'],
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
    name='david_assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # Clean desktop application window (no background CMD window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / 'assets' / 'david_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='david_assistant',
)
