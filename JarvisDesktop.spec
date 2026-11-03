# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all


datas = [('app/static', 'app/static'), ('desktop', 'desktop')]
binaries = []
hiddenimports = [
    'app.adapters.edge.network_discovery_adapter',
    'app.adapters.infrastructure.routers.intelligence_dashboard',
    'app.domain.intelligence.contracts',
]

for package in ('webview', 'clr_loader', 'pythonnet'):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports


a = Analysis(
    ['app/adapters/edge/jarvis_desktop_shell.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='JarvisDesktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['desktop/jarvis.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JarvisDesktop',
)
