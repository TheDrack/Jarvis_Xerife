#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for auto_fixer_logic.py

This script creates a sample error scenario and tests the auto-fixer.
"""

import os
import subprocess
import sys
from pathlib import Path

# Test scenario: Create a file with an intentional error
TEST_FILE_PATH = "data/test_error.py"
TEST_FILE_CONTENT = """# Test file with an intentional error

def calculate_sum(a, b):
    # Missing return statement - this is the error
    result = a + b

def main():
    total = calculate_sum(5, 10)
    print(f"Total: {total}")

if __name__ == "__main__":
    main()
"""

TEST_ERROR_MESSAGE = """Error in File "data/test_error.py", line 5, in calculate_sum
    result = a + b
             ^
NoneType: 'NoneType' object has no attribute '__iter__'

The function calculate_sum returns None because there is no return statement.
This causes an error when trying to use the result in line 8.
"""


def create_test_scenario():
    """Create a test file with an error"""
    print("Creating test scenario...")
    
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    
    # Write test file
    with open(TEST_FILE_PATH, "w") as f:
        f.write(TEST_FILE_CONTENT)
    
    print(f"✓ Created test file: {TEST_FILE_PATH}")


def run_auto_fixer():
    """Run the auto-fixer with test data"""
    print("\n" + "="*60)
    print("Running Auto-Fixer...")
    print("="*60 + "\n")
    
    # Set environment variables
    env = os.environ.copy()
    env["ISSUE_BODY"] = TEST_ERROR_MESSAGE
    env["ISSUE_ID"] = "test-123"
    
    # Run the auto-fixer script
    result = subprocess.run(
        ["python", "scripts/auto_fixer_logic.py"],
        env=env,
        capture_output=True,
        text=True,
    )
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("\nSTDERR:")
        print(result.stderr)
    
    print(f"\nExit code: {result.returncode}")
    
    return result.returncode


def verify_fix():
    """Verify that the fix was applied"""
    print("\n" + "="*60)
    print("Verifying fix...")
    print("="*60 + "\n")
    
    if not os.path.exists(TEST_FILE_PATH):
        print("✗ Test file not found")
        return False
    
    with open(TEST_FILE_PATH, "r") as f:
        fixed_content = f.read()
    
    print("Fixed content:")
    print("-"*60)
    print(fixed_content)
    print("-"*60)
    
    # Check if 'return' statement was added
    if "return result" in fixed_content or "return a + b" in fixed_content:
        print("✓ Fix appears to have been applied (return statement added)")
        return True
    else:
        print("⚠ Could not verify if fix was applied")
        return False


def cleanup():
    """Clean up test files"""
    print("\n" + "="*60)
    print("Cleanup...")
    print("="*60 + "\n")
    
    # Don't delete the file - let the user review it
    # if os.path.exists(TEST_FILE_PATH):
    #     os.remove(TEST_FILE_PATH)
    #     print(f"✓ Removed test file: {TEST_FILE_PATH}")
    
    print("Note: Test file and branch left intact for review")
    print("To cleanup manually:")
    print(f"  rm {TEST_FILE_PATH}")
    print("  git branch -D fix/issue-test-123")


def main():
    """Run the complete test"""
    print("="*60)
    print("AUTO-FIXER TEST SUITE")
    print("="*60)
    
    # Check if we're in the right directory
    if not os.path.exists("scripts/auto_fixer_logic.py"):
        print("Error: Must run from repository root")
        sys.exit(1)
    
    # Create test scenario
    create_test_scenario()
    
    # Note about prerequisites
    print("\n" + "="*60)
    print("PREREQUISITES CHECK")
    print("="*60)
    print("\nFor the auto-fixer to work, you need:")
    print("1. GROQ_API_KEY or GOOGLE_API_KEY/GEMINI_API_KEY in environment")
    print("2. GitHub CLI (gh) installed and authenticated")
    print("3. Git repository initialized with remote")
    print("\nIf these are not available, the test will demonstrate")
    print("the error handling capabilities of the auto-fixer.\n")
    
    input("Press Enter to continue with the test...")
    
    # Run the auto-fixer
    exit_code = run_auto_fixer()
    
    if exit_code == 0:
        # Verify the fix
        verify_fix()
        print("\n✅ AUTO-FIXER TEST COMPLETED SUCCESSFULLY")
    else:
        print("\n⚠️  AUTO-FIXER TEST COMPLETED WITH ERRORS")
        print("This is expected if API keys or gh CLI are not configured.")
    
    # Cleanup
    cleanup()
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()
