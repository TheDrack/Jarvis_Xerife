#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Demo script for ExtensionManager - uv-based package management

This script demonstrates the ExtensionManager's capabilities:
1. Installing packages using uv (with fallback to pip)
2. Intelligent package checking to avoid redundant installations
3. Pre-warming recommended libraries for data tasks
4. Logging of successful installations
"""

import logging
import sys

from app.application.services import ExtensionManager

# Configure logging to see the ExtensionManager in action
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def demo_basic_installation():
    """Demonstrate basic package installation"""
    print("\n" + "="*80)
    print("DEMO 1: Basic Package Installation")
    print("="*80)
    
    manager = ExtensionManager()
    
    # Try to install a package (will check if already installed first)
    print("\n1. Installing requests library...")
    success = manager.install_package("requests")
    if success:
        print("   ✅ requests installation successful!")
    else:
        print("   ❌ requests installation failed!")
    
    # Try to install again (should skip as it's already installed)
    print("\n2. Attempting to install requests again...")
    success = manager.install_package("requests")
    if success:
        print("   ✅ Detected already installed, skipped redundant installation!")


def demo_package_mapping():
    """Demonstrate package name mapping"""
    print("\n" + "="*80)
    print("DEMO 2: Package Name Mapping")
    print("="*80)
    
    manager = ExtensionManager()
    
    # Install opencv (maps to opencv-python)
    print("\n1. Installing 'opencv' (maps to 'opencv-python')...")
    print("   Note: opencv is imported as 'cv2'")
    # We won't actually install opencv here as it's large
    print("   (Skipping actual installation in demo)")
    
    # Show the mapping
    print("\n2. Package mappings:")
    for capability, package in manager.CAPABILITY_PACKAGES.items():
        if capability != package:
            print(f"   - {capability:20s} → {package}")


def demo_recommended_libraries():
    """Demonstrate pre-warming with recommended libraries"""
    print("\n" + "="*80)
    print("DEMO 3: Pre-warming Recommended Libraries")
    print("="*80)
    
    manager = ExtensionManager()
    
    print(f"\nRecommended libraries for data tasks: {', '.join(manager.RECOMMENDED_LIBRARIES)}")
    
    # Check which ones are installed
    print("\nChecking installation status:")
    for lib in manager.RECOMMENDED_LIBRARIES:
        installed = manager.is_package_installed(lib)
        status = "✅ Installed" if installed else "❌ Not installed"
        print(f"   - {lib:15s}: {status}")
    
    # Note about pre-warming
    print("\nNote: In production, you can call ensure_recommended_libraries()")
    print("      to automatically install all missing recommended libraries.")


def demo_data_task_detection():
    """Demonstrate automatic installation for data tasks"""
    print("\n" + "="*80)
    print("DEMO 4: Automatic Installation for Data Tasks")
    print("="*80)
    
    manager = ExtensionManager()
    
    print("\nWhen Jarvis detects a data task, it can automatically ensure")
    print("recommended libraries are installed using check_and_install_for_data_task()")
    
    print("\n(This would install pandas, numpy, and matplotlib if missing)")


def demo_uv_vs_pip():
    """Demonstrate uv vs pip detection"""
    print("\n" + "="*80)
    print("DEMO 5: UV vs PIP Detection")
    print("="*80)
    
    # Try with uv
    manager_uv = ExtensionManager(use_uv=True)
    print(f"\n1. ExtensionManager with use_uv=True:")
    print(f"   Using: {'uv' if manager_uv._use_uv else 'pip (fallback)'}")
    
    # Force pip
    manager_pip = ExtensionManager(use_uv=False)
    print(f"\n2. ExtensionManager with use_uv=False:")
    print(f"   Using: {'uv' if manager_pip._use_uv else 'pip'}")


def main():
    """Run all demonstrations"""
    print("\n" + "="*80)
    print(" ExtensionManager Demo - Modern Package Management with UV")
    print("="*80)
    
    try:
        demo_basic_installation()
        demo_package_mapping()
        demo_recommended_libraries()
        demo_data_task_detection()
        demo_uv_vs_pip()
        
        print("\n" + "="*80)
        print("Demo completed successfully! ✅")
        print("="*80)
        print("\nThe ExtensionManager provides:")
        print("  1. ✅ Intelligent package installation with uv (fallback to pip)")
        print("  2. ✅ Redundancy checking to avoid duplicate installations")
        print("  3. ✅ Pre-warming for recommended libraries")
        print("  4. ✅ Automatic detection and installation for data tasks")
        print("  5. ✅ Comprehensive logging of installation activities")
        print("\nIntegration with FastAPI:")
        print("  - POST /v1/extensions/install - Install packages in background")
        print("  - GET  /v1/extensions/status/{package} - Check installation status")
        print("  - POST /v1/extensions/prewarm - Pre-warm recommended libraries")
        print("\n")
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error in demo: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
