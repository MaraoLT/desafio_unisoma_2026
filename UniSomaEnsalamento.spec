# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import sys
from pathlib import Path

block_cipher = None

datas = [
    ('src/app/static', 'src/app/static'),
    ('src/app/images', 'src/app/images'),
    ('instances/public', 'instances/public'),
]

try:
    datas += collect_data_files('pulp')
except Exception:
    pass

hiddenimports = [
    'bottle',
    'webview',
    'openpyxl',
    'pulp',
    'reportlab',
    'reportlab.lib.colors',
    'reportlab.lib.pagesizes',
    'reportlab.lib.units',
    'reportlab.lib.styles',
    'reportlab.platypus',
    'reportlab.pdfgen.canvas',
    'src.read_instance',
    'src.pre_process',
    'src.pos_process',
    'src.models.solver',
    'src.app.server',
    'src.app.pdf_lists',
    'src.app.tutorial_pdf',
]

try:
    hiddenimports += collect_submodules('pulp')
except Exception:
    pass

a = Analysis(
    ['src/app/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='AlocaABC',
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
    icon='src/app/images/app_icon.ico',
)
