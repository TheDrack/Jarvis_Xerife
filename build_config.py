# -*- coding: utf-8 -*-
"""
PyInstaller Build Configuration for Jarvis Universal Installer

This script creates a standalone executable for Windows using PyInstaller.
The executable includes all necessary dependencies and can be distributed
as a single file.

Usage:
    python build_config.py

Or directly with PyInstaller:
    pyinstaller --clean jarvis_installer.spec
"""

import sys
import io
from pathlib import Path

# Force Python to handle encoding errors gracefully
if hasattr(sys.stdout, 'buffer') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# PyInstaller configuration
APP_NAME = "Jarvis_Installer"
SCRIPT_PATH = "main.py"
ICON_PATH = None  # Set to your icon file path if available (e.g., "icon.ico")

# Build directory
BUILD_DIR = Path("build")
DIST_DIR = Path("dist")

# Hidden imports - libraries that PyInstaller might miss
HIDDEN_IMPORTS = [
    # Core dependencies
    'pydantic',
    'pydantic_settings',
    'pydantic.deprecated.decorator',
    'pydantic.json_schema',
    'dotenv',
    'google.generativeai',
    
    # Database
    'sqlmodel',
    'sqlalchemy',
    'sqlalchemy.sql.default_comparator',
    
    # Edge dependencies
    'pyttsx3',
    'pyttsx3.drivers',
    'pyttsx3.drivers.sapi5',
    'speech_recognition',
    'pyautogui',
    'pynput',
    'pynput.keyboard',
    'pynput.mouse',
    'pyperclip',
    
    # API server
    'fastapi',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    
    # Security
    'passlib',
    'passlib.handlers',
    'passlib.handlers.bcrypt',
    'jose',
    'jose.jwt',
    
    # App modules
    'app',
    'app.core',
    'app.core.config',
    'app.domain',
    'app.application',
    'app.adapters',
    'app.adapters.infrastructure',
    'app.adapters.infrastructure.setup_wizard',
    'app.adapters.edge',
    'app.bootstrap_edge',
    'app.container',
]

# Data files to include
DATA_FILES = [
    ('.env.example', '.'),  # Include .env.example as reference
]

# Excluded modules (to reduce size)
# Note: Only exclude modules that are not used by the application
EXCLUDED_MODULES = [
    'matplotlib',
    'PIL',
    'tkinter',
]


def create_spec_file():
    """Create PyInstaller spec file"""
    
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{SCRIPT_PATH}'],
    pathex=[],
    binaries=[],
    datas={DATA_FILES},
    hiddenimports={HIDDEN_IMPORTS},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={EXCLUDED_MODULES},
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
    name='{APP_NAME}',
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
    icon={repr(ICON_PATH) if ICON_PATH else None},
)
"""
    
    spec_file = Path(f"{APP_NAME.lower()}.spec")
    with open(spec_file, 'w', encoding='utf-8') as f:
        f.write(spec_content)
    
    print(f"[OK] Created spec file: {spec_file}")
    return spec_file


def build_executable():
    """Build executable using PyInstaller"""
    
    try:
        import PyInstaller.__main__
    except ImportError:
        print("[X] PyInstaller not found. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        import PyInstaller.__main__
    
    # Create spec file
    spec_file = create_spec_file()
    
    print("\nBuilding executable with PyInstaller...")
    print("This may take a few minutes...\n")
    
    # Run PyInstaller
    PyInstaller.__main__.run([
        str(spec_file),
        '--clean',
        '--noconfirm',
    ])
    
    # Check if executable was created
    exe_path = DIST_DIR / f"{APP_NAME}.exe"
    if exe_path.exists():
        print(f"\n[OK] Build successful!")
        print(f"[OK] Executable created: {exe_path}")
        print(f"[OK] Size: {exe_path.stat().st_size / (1024*1024):.2f} MB")
    else:
        print(f"\n[X] Build failed - executable not found")
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 60)
    print("Jarvis Universal Installer - Build Script")
    print("=" * 60)
    print()
    
    build_executable()
    
    print("\n" + "=" * 60)
    print("Build completed successfully!")
    print("=" * 60)
