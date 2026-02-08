#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Integration test for auto_fixer_logic.py enhancements

Simulates real-world scenarios without requiring actual API calls
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from auto_fixer_logic import AutoFixer


def test_integration_scenario_1():
    """Scenario: User wants to update README with lowercase mention"""
    print("\n" + "="*70)
    print("SCENARIO 1: Update readme (lowercase mention)")
    print("="*70)
    
    issue_body = """
    Hi! I would like to update the readme file to include 
    information about how to contribute to this project.
    """
    
    fixer = AutoFixer()
    
    # Step 1: Check if this is a documentation request
    is_doc = fixer.is_documentation_request(issue_body)
    print(f"1. Is documentation request? {is_doc}")
    assert is_doc == False, "Should not detect 'information about' as doc request"
    
    # Step 2: Try to extract from traceback (should fail)
    from_traceback = fixer.extract_file_from_error(issue_body)
    print(f"2. File from traceback? {from_traceback}")
    assert from_traceback is None, "Should not find traceback"
    
    # Step 3: Try to find common filename (should succeed)
    from_common = fixer.extract_common_filename(issue_body)
    print(f"3. File from common names? {from_common}")
    assert from_common == "README.md", f"Expected README.md, got {from_common}"
    
    print("✓ SCENARIO 1 PASSED: Successfully identified README.md from 'readme' mention")


def test_integration_scenario_2():
    """Scenario: Documentation update request in Portuguese"""
    print("\n" + "="*70)
    print("SCENARIO 2: Documentation update request (Portuguese)")
    print("="*70)
    
    issue_body = """
    Por favor, adicionar uma seção sobre instalação ao README.
    A seção deve incluir instruções para diferentes sistemas operacionais.
    """
    
    fixer = AutoFixer()
    
    # Step 1: Detect documentation request
    is_doc = fixer.is_documentation_request(issue_body)
    print(f"1. Is documentation request? {is_doc}")
    assert is_doc == True, "Should detect Portuguese 'adicionar uma seção'"
    
    # Step 2: Find the file
    file_path = fixer.extract_file_from_error(issue_body)
    if not file_path:
        file_path = fixer.extract_common_filename(issue_body)
    print(f"2. Target file? {file_path}")
    assert file_path == "README.md", f"Expected README.md, got {file_path}"
    
    # Step 3: Verify file exists
    full_path = fixer.repo_path / file_path
    exists = full_path.exists()
    print(f"3. File exists? {exists}")
    assert exists == True, "README.md should exist"
    
    print("✓ SCENARIO 2 PASSED: Correctly handled Portuguese documentation request")


def test_integration_scenario_3():
    """Scenario: Bug fix with traceback"""
    print("\n" + "="*70)
    print("SCENARIO 3: Bug fix with traceback (original functionality)")
    print("="*70)
    
    issue_body = """
    Error: NameError in execution
    
    Traceback (most recent call last):
      File "scripts/auto_fixer_logic.py", line 42, in <module>
        result = undefined_variable
    NameError: name 'undefined_variable' is not defined
    """
    
    fixer = AutoFixer()
    
    # Step 1: Not a documentation request
    is_doc = fixer.is_documentation_request(issue_body)
    print(f"1. Is documentation request? {is_doc}")
    assert is_doc == False, "Should not be detected as doc request"
    
    # Step 2: Extract file from traceback
    file_path = fixer.extract_file_from_error(issue_body)
    print(f"2. File from traceback? {file_path}")
    assert file_path == "scripts/auto_fixer_logic.py", f"Expected scripts/auto_fixer_logic.py, got {file_path}"
    
    # Step 3: Verify file exists
    full_path = fixer.repo_path / file_path
    exists = full_path.exists()
    print(f"3. File exists? {exists}")
    assert exists == True, "File should exist"
    
    print("✓ SCENARIO 3 PASSED: Original traceback extraction still works")


def test_integration_scenario_4():
    """Scenario: Requirements file update"""
    print("\n" + "="*70)
    print("SCENARIO 4: Requirements file update")
    print("="*70)
    
    issue_body = """
    We need to add pytest to the requirements for testing.
    Also, please add coverage tool.
    """
    
    fixer = AutoFixer()
    
    # Step 1: Detect if documentation request (might not be)
    is_doc = fixer.is_documentation_request(issue_body)
    print(f"1. Is documentation request? {is_doc}")
    
    # Step 2: Find requirements file
    file_path = fixer.extract_file_from_error(issue_body)
    if not file_path:
        file_path = fixer.extract_common_filename(issue_body)
    print(f"2. Target file? {file_path}")
    assert file_path == "requirements.txt", f"Expected requirements.txt, got {file_path}"
    
    # Step 3: Verify file exists
    full_path = fixer.repo_path / file_path
    exists = full_path.exists()
    print(f"3. File exists? {exists}")
    assert exists == True, "requirements.txt should exist"
    
    print("✓ SCENARIO 4 PASSED: Successfully identified requirements.txt")


def test_integration_scenario_5():
    """Scenario: Missing API keys"""
    print("\n" + "="*70)
    print("SCENARIO 5: Missing API keys (error handling)")
    print("="*70)
    
    # Save and remove API keys
    saved_keys = {}
    for key in ["GROQ_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"]:
        saved_keys[key] = os.environ.get(key)
        if key in os.environ:
            del os.environ[key]
    
    try:
        fixer = AutoFixer()
        
        # Step 1: Check that keys are not set
        print(f"1. GROQ key set? {fixer.groq_api_key is not None}")
        print(f"2. Gemini key set? {fixer.gemini_api_key is not None}")
        assert fixer.groq_api_key is None, "GROQ key should be None"
        assert fixer.gemini_api_key is None, "Gemini key should be None"
        
        # Step 2: Try to call API (should fail gracefully)
        result = fixer.call_groq_api("test", "test code")
        print(f"3. Groq API result (without key)? {result}")
        assert result is None, "Should return None without key"
        
        result = fixer.call_gemini_api("test", "test code")
        print(f"4. Gemini API result (without key)? {result}")
        assert result is None, "Should return None without key"
        
        print("✓ SCENARIO 5 PASSED: Missing API keys handled gracefully")
        
    finally:
        # Restore API keys
        for key, value in saved_keys.items():
            if value is not None:
                os.environ[key] = value


def test_integration_scenario_6():
    """Scenario: English documentation request"""
    print("\n" + "="*70)
    print("SCENARIO 6: English documentation request")
    print("="*70)
    
    issue_body = """
    Please add a section about testing to the README.
    Include examples of how to run unit tests and integration tests.
    """
    
    fixer = AutoFixer()
    
    # Step 1: Detect documentation request
    is_doc = fixer.is_documentation_request(issue_body)
    print(f"1. Is documentation request? {is_doc}")
    assert is_doc == True, "Should detect 'add a section'"
    
    # Step 2: Find the file
    file_path = fixer.extract_file_from_error(issue_body)
    if not file_path:
        file_path = fixer.extract_common_filename(issue_body)
    print(f"2. Target file? {file_path}")
    assert file_path == "README.md", f"Expected README.md, got {file_path}"
    
    print("✓ SCENARIO 6 PASSED: English documentation request detected")


def main():
    """Run all integration scenarios"""
    print("\n" + "="*70)
    print("AUTO-FIXER INTEGRATION TEST SUITE")
    print("="*70)
    print("\nTesting real-world scenarios without API calls...")
    
    try:
        test_integration_scenario_1()
        test_integration_scenario_2()
        test_integration_scenario_3()
        test_integration_scenario_4()
        test_integration_scenario_5()
        test_integration_scenario_6()
        
        print("\n" + "="*70)
        print("✅ ALL INTEGRATION SCENARIOS PASSED!")
        print("="*70)
        print("\nThe auto-fixer correctly handles:")
        print("1. ✓ Lowercase file mentions (readme → README.md)")
        print("2. ✓ Portuguese documentation requests")
        print("3. ✓ Traditional bug fixes with tracebacks")
        print("4. ✓ Requirements file updates")
        print("5. ✓ Missing API key scenarios")
        print("6. ✓ English documentation requests")
        print("\nAll scenarios simulate the complete workflow from")
        print("issue detection to file identification.")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ INTEGRATION TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
