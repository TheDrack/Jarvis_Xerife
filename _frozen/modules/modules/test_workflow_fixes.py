#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to validate the workflow fixes for metabolism and auto-evolution.

This script tests:
1. metabolism_analyzer.py outputs are correct
2. metabolism_mutator.py handles errors gracefully
3. auto_evolution service works properly
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_metabolism_analyzer():
    """Test that metabolism_analyzer.py produces correct outputs"""
    print("=" * 60)
    print("TEST 1: Metabolism Analyzer")
    print("=" * 60)
    
    # Use context manager for automatic cleanup
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        output_file = f.name
    
    try:
        env = os.environ.copy()
        env['GITHUB_OUTPUT'] = output_file
        
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / 'scripts' / 'metabolism_analyzer.py'),
                '--intent', 'test',
                '--instruction', 'Test the analyzer',
                '--context', 'Test context with sufficient length to pass validation',
                '--event-type', 'test'
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=PROJECT_ROOT
        )
        
        # Check outputs were written
        with open(output_file, 'r') as f:
            outputs = f.read()
        
        print(f"Exit code: {result.returncode}")
        print(f"Outputs written:\n{outputs}")
        
        # Validate outputs
        assert 'requires_human=' in outputs, "Missing requires_human output"
        assert 'intent_type=' in outputs, "Missing intent_type output"
        assert 'impact_type=' in outputs, "Missing impact_type output"
        assert 'mutation_strategy=' in outputs, "Missing mutation_strategy output"
        
        # Check that mutation_strategy is not "None"
        for line in outputs.split('\n'):
            if line.startswith('mutation_strategy='):
                value = line.split('=', 1)[1]
                assert value != 'None', "mutation_strategy should not be 'None'"
        
        print("✅ TEST 1 PASSED: Analyzer produces correct outputs")
        return True
        
    except Exception as e:
        print(f"❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Always cleanup the temporary file
        try:
            if os.path.exists(output_file):
                os.unlink(output_file)
        except Exception:
            pass  # Best effort cleanup


def test_metabolism_mutator():
    """Test that metabolism_mutator.py handles operations correctly"""
    print("\n" + "=" * 60)
    print("TEST 2: Metabolism Mutator")
    print("=" * 60)
    
    # Use context manager for automatic cleanup
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        output_file = f.name
    
    try:
        env = os.environ.copy()
        env['GITHUB_OUTPUT'] = output_file
        
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / 'scripts' / 'metabolism_mutator.py'),
                '--strategy', 'minimal_change',
                '--intent', 'test',
                '--impact', 'test'
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=PROJECT_ROOT
        )
        
        print(f"Exit code: {result.returncode}")
        print(f"Output: {result.stdout[-500:]}")  # Last 500 chars
        
        # Should succeed with exit code 0
        assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}"
        
        # Check for success message
        assert '"success": true' in result.stdout, "Expected success=true in output"
        
        print("✅ TEST 2 PASSED: Mutator executes successfully")
        return True
        
    except Exception as e:
        print(f"❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Always cleanup the temporary file
        try:
            if os.path.exists(output_file):
                os.unlink(output_file)
        except Exception:
            pass  # Best effort cleanup


def test_auto_evolution_service():
    """Test that auto_evolution service can find missions"""
    print("\n" + "=" * 60)
    print("TEST 3: Auto Evolution Service")
    print("=" * 60)
    
    try:
        from app.application.services.auto_evolution import AutoEvolutionService
        
        service = AutoEvolutionService()
        
        # Test parse_roadmap
        roadmap = service.parse_roadmap()
        print(f"Parsed roadmap with {roadmap.get('total_sections', 0)} sections")
        
        assert 'sections' in roadmap, "Roadmap should have sections"
        
        # Test find_next_mission
        mission = service.find_next_mission()
        if mission:
            print(f"Found mission: {mission['mission']['description'][:50]}...")
            print(f"Section: {mission['section']}, Priority: {mission['priority']}")
        else:
            print("No mission found (all complete)")
        
        # Test is_auto_evolution_pr
        is_auto = service.is_auto_evolution_pr(
            pr_title="[Auto-Evolution] Test PR",
            pr_body="Auto evolution test"
        )
        assert is_auto == True, "Should detect auto-evolution PR"
        
        is_not_auto = service.is_auto_evolution_pr(
            pr_title="Fix: regular bug fix",
            pr_body="Regular fix"
        )
        assert is_not_auto == False, "Should not detect regular PR as auto-evolution"
        
        print("✅ TEST 3 PASSED: Auto evolution service works correctly")
        return True
        
    except Exception as e:
        print(f"❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("WORKFLOW FIXES VALIDATION TEST SUITE")
    print("=" * 60 + "\n")
    
    results = []
    
    # Run tests
    results.append(("Metabolism Analyzer", test_metabolism_analyzer()))
    results.append(("Metabolism Mutator", test_metabolism_mutator()))
    results.append(("Auto Evolution Service", test_auto_evolution_service()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Workflows should work correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review errors above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
