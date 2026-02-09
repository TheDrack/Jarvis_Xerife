#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for auto_fixer_logic.py enhancements

Tests the new features added:
1. File Flexibility - Common filename detection
2. API Validation - Better error messages
3. Context Handling - Documentation request detection
"""

import sys
import os

# Add repository root to path to import from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.auto_fixer_logic import AutoFixer


def test_common_filename_detection():
    """Test detection of common filenames in issue body"""
    print("\n" + "="*60)
    print("TEST 1: Common Filename Detection")
    print("="*60)
    
    fixer = AutoFixer()
    
    # Test case 1: lowercase readme
    issue_body = "Please update the readme.md file to include installation instructions"
    result = fixer.extract_common_filename(issue_body)
    print(f"\n1. Test lowercase 'readme.md':")
    print(f"   Issue: {issue_body[:50]}...")
    print(f"   Result: {result}")
    assert result == "README.md", f"Expected 'README.md', got '{result}'"
    print("   ✓ PASS")
    
    # Test case 2: requirements.txt
    issue_body = "The requirements file needs to be updated with new dependencies"
    result = fixer.extract_common_filename(issue_body)
    print(f"\n2. Test 'requirements' mention:")
    print(f"   Issue: {issue_body[:50]}...")
    print(f"   Result: {result}")
    assert result == "requirements.txt", f"Expected 'requirements.txt', got '{result}'"
    print("   ✓ PASS")
    
    # Test case 3: README in uppercase
    issue_body = "Update README to add badges"
    result = fixer.extract_common_filename(issue_body)
    print(f"\n3. Test uppercase 'README':")
    print(f"   Issue: {issue_body[:50]}...")
    print(f"   Result: {result}")
    assert result == "README.md", f"Expected 'README.md', got '{result}'"
    print("   ✓ PASS")
    
    # Test case 4: No common file
    issue_body = "Fix the bug in the database connection"
    result = fixer.extract_common_filename(issue_body)
    print(f"\n4. Test no common file:")
    print(f"   Issue: {issue_body[:50]}...")
    print(f"   Result: {result}")
    assert result is None, f"Expected None, got '{result}'"
    print("   ✓ PASS")
    
    print("\n✅ All common filename detection tests passed!")


def test_documentation_request_detection():
    """Test detection of documentation update requests"""
    print("\n" + "="*60)
    print("TEST 2: Documentation Request Detection")
    print("="*60)
    
    fixer = AutoFixer()
    
    # Test case 1: Portuguese "adicionar uma seção"
    issue_body = "Por favor, adicionar uma seção sobre instalação ao README"
    result = fixer.is_documentation_request(issue_body)
    print(f"\n1. Test Portuguese 'adicionar uma seção':")
    print(f"   Issue: {issue_body[:50]}...")
    print(f"   Result: {result}")
    assert result == True, f"Expected True, got {result}"
    print("   ✓ PASS")
    
    # Test case 2: English "add section"
    issue_body = "Add section about contributing to the documentation"
    result = fixer.is_documentation_request(issue_body)
    print(f"\n2. Test English 'add section':")
    print(f"   Issue: {issue_body[:50]}...")
    print(f"   Result: {result}")
    assert result == True, f"Expected True, got {result}"
    print("   ✓ PASS")
    
    # Test case 3: Update readme
    issue_body = "Update README with new features"
    result = fixer.is_documentation_request(issue_body)
    print(f"\n3. Test 'update readme':")
    print(f"   Issue: {issue_body[:50]}...")
    print(f"   Result: {result}")
    assert result == True, f"Expected True, got {result}"
    print("   ✓ PASS")
    
    # Test case 4: Bug fix (not documentation)
    issue_body = "Fix NameError in app/main.py line 42"
    result = fixer.is_documentation_request(issue_body)
    print(f"\n4. Test bug fix (not documentation):")
    print(f"   Issue: {issue_body[:50]}...")
    print(f"   Result: {result}")
    assert result == False, f"Expected False, got {result}"
    print("   ✓ PASS")
    
    print("\n✅ All documentation request detection tests passed!")


def test_file_extraction_fallback():
    """Test that file extraction falls back to common filename detection"""
    print("\n" + "="*60)
    print("TEST 3: File Extraction with Fallback")
    print("="*60)
    
    fixer = AutoFixer()
    
    # Test case 1: No traceback, but mentions readme
    issue_body = "The readme should include a section about testing"
    
    # First try to extract from error (should fail)
    result_traceback = fixer.extract_file_from_error(issue_body)
    print(f"\n1. Extract from traceback:")
    print(f"   Result: {result_traceback}")
    assert result_traceback is None, "Should not find file in traceback"
    print("   ✓ No traceback found (expected)")
    
    # Then try common filename extraction (should succeed)
    result_common = fixer.extract_common_filename(issue_body)
    print(f"\n2. Extract common filename:")
    print(f"   Result: {result_common}")
    assert result_common == "README.md", f"Expected 'README.md', got '{result_common}'"
    print("   ✓ Found README.md via common filename detection")
    
    # Test case 2: Has traceback (should use it)
    issue_body_with_traceback = """
    Error in File "app/main.py", line 42
    NameError: name 'x' is not defined
    """
    
    result_traceback = fixer.extract_file_from_error(issue_body_with_traceback)
    print(f"\n3. Extract from traceback (when present):")
    print(f"   Result: {result_traceback}")
    assert result_traceback == "app/main.py", f"Expected 'app/main.py', got '{result_traceback}'"
    print("   ✓ Correctly extracted from traceback")
    
    print("\n✅ All file extraction fallback tests passed!")


def test_keyword_based_file_suggestion():
    """Test keyword-based file suggestion feature"""
    print("\n" + "="*60)
    print("TEST 4: Keyword-Based File Suggestion")
    print("="*60)
    
    fixer = AutoFixer()
    
    # Test case 1: 'interface' keyword
    issue_body = "I need to improve the interface of the application"
    result = fixer.suggest_file_by_keywords(issue_body)
    print(f"\n1. Test 'interface' keyword:")
    print(f"   Issue: {issue_body}")
    print(f"   Result: {result}")
    # Should suggest app/main.py or main.py depending on what exists
    assert result is not None, "Should suggest a file for 'interface' keyword"
    assert result in ["app/main.py", "main.py"], f"Expected app/main.py or main.py, got '{result}'"
    print(f"   ✓ PASS - Suggested: {result}")
    
    # Test case 2: 'api' keyword
    issue_body = "The api endpoint is not working properly"
    result = fixer.suggest_file_by_keywords(issue_body)
    print(f"\n2. Test 'api' keyword:")
    print(f"   Issue: {issue_body}")
    print(f"   Result: {result}")
    assert result is not None, "Should suggest a file for 'api' keyword"
    print(f"   ✓ PASS - Suggested: {result}")
    
    # Test case 3: 'frontend' keyword
    issue_body = "Need to update the frontend components"
    result = fixer.suggest_file_by_keywords(issue_body)
    print(f"\n3. Test 'frontend' keyword:")
    print(f"   Issue: {issue_body}")
    print(f"   Result: {result}")
    assert result is not None, "Should suggest a file for 'frontend' keyword"
    print(f"   ✓ PASS - Suggested: {result}")
    
    # Test case 4: No keywords
    issue_body = "There is a bug somewhere"
    result = fixer.suggest_file_by_keywords(issue_body)
    print(f"\n4. Test no keywords:")
    print(f"   Issue: {issue_body}")
    print(f"   Result: {result}")
    assert result is None, f"Expected None, got '{result}'"
    print("   ✓ PASS - No suggestion (expected)")
    
    # Test case 5: Mixed case keywords
    issue_body = "The API Interface needs improvements"
    result = fixer.suggest_file_by_keywords(issue_body)
    print(f"\n5. Test mixed case 'API Interface':")
    print(f"   Issue: {issue_body}")
    print(f"   Result: {result}")
    assert result is not None, "Should suggest a file for 'api' keyword (case insensitive)"
    print(f"   ✓ PASS - Suggested: {result}")
    
    print("\n✅ All keyword-based file suggestion tests passed!")


def test_api_key_validation():
    """Test API key validation and error messages"""
    print("\n" + "="*60)
    print("TEST 4: API Key Validation")
    print("="*60)
    
    # Save original environment
    original_groq = os.environ.get("GROQ_API_KEY")
    original_google = os.environ.get("GOOGLE_API_KEY")
    original_gemini = os.environ.get("GEMINI_API_KEY")
    
    try:
        # Remove all API keys
        for key in ["GROQ_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"]:
            if key in os.environ:
                del os.environ[key]
        
        print("\n1. Test initialization without API keys:")
        print("   (Should show clear error message)")
        fixer = AutoFixer()
        
        assert fixer.groq_api_key is None, "GROQ_API_KEY should be None"
        assert fixer.gemini_api_key is None, "GEMINI_API_KEY should be None"
        print("   ✓ Correctly detected missing API keys")
        
        # Test that the error is clear when trying to use the API
        print("\n2. Test API call without keys:")
        result = fixer.call_groq_api("test error", "test code")
        assert result is None, "Should return None without API key"
        print("   ✓ Correctly returned None for Groq API")
        
        result = fixer.call_gemini_api("test error", "test code")
        assert result is None, "Should return None without API key"
        print("   ✓ Correctly returned None for Gemini API")
        
    finally:
        # Restore original environment
        if original_groq:
            os.environ["GROQ_API_KEY"] = original_groq
        if original_google:
            os.environ["GOOGLE_API_KEY"] = original_google
        if original_gemini:
            os.environ["GEMINI_API_KEY"] = original_gemini
    
    print("\n✅ All API key validation tests passed!")


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("AUTO-FIXER ENHANCEMENTS TEST SUITE")
    print("="*70)
    
    try:
        test_common_filename_detection()
        test_documentation_request_detection()
        test_file_extraction_fallback()
        test_keyword_based_file_suggestion()
        test_api_key_validation()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED!")
        print("="*70)
        print("\nThe following enhancements have been validated:")
        print("1. ✓ File Flexibility - Common filename detection works")
        print("2. ✓ API Validation - Clear error messages for missing keys")
        print("3. ✓ Context Handling - Documentation request detection works")
        print("4. ✓ Keyword Suggestions - File suggestions based on keywords")
        print("\nThe auto-fixer can now:")
        print("- Handle documentation updates (not just bug fixes)")
        print("- Find files mentioned in issues (not just in tracebacks)")
        print("- Suggest files based on keywords (interface, api, frontend)")
        print("- Provide clear feedback when API keys are missing")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
