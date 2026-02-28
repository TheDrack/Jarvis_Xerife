#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Demonstration of DependencyManager on-demand capability installation

This script demonstrates how the DependencyManager can check for and install
packages on demand, allowing Jarvis to extend its capabilities at runtime.
"""

from app.application.services import DependencyManager


def main():
    print("=" * 60)
    print("DependencyManager Demo - On-Demand Capabilities")
    print("=" * 60)
    print()

    # Create a DependencyManager instance
    manager = DependencyManager()

    # Test 1: Check for a built-in module (should always be available)
    print("Test 1: Checking for built-in module 'sys'")
    if manager.ensure_capability("sys"):
        print("✓ 'sys' module is available")
    else:
        print("✗ 'sys' module is NOT available (unexpected)")
    print()

    # Test 2: Check for a commonly installed module
    print("Test 2: Checking for 'json' module")
    if manager.ensure_capability("json"):
        print("✓ 'json' module is available")
    else:
        print("✗ 'json' module is NOT available")
    print()

    # Test 3: Show capability mapping
    print("Test 3: Capability Package Mapping")
    print("The following capabilities have special package names:")
    for capability, package in manager.CAPABILITY_PACKAGES.items():
        if capability != package:
            print(f"  - '{capability}' installs as '{package}'")
    print()

    # Test 4: Show installed capabilities
    print("Test 4: Currently confirmed capabilities")
    capabilities = manager.get_installed_capabilities()
    if capabilities:
        for cap in sorted(capabilities):
            print(f"  - {cap}")
    else:
        print("  (none confirmed yet)")
    print()

    # Test 5: Check availability without installing
    print("Test 5: Non-intrusive availability check")
    test_modules = ["os", "sys", "json"]
    for module in test_modules:
        available = manager.is_capability_available(module)
        status = "✓ Available" if available else "✗ Not available"
        print(f"  {module}: {status}")
    print()

    print("=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
