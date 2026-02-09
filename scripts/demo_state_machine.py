#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Integration test demonstrating the Self-Healing State Machine

This script simulates the complete workflow:
1. Creates a file with an intentional error
2. Generates a pytest report
3. Runs the state machine to identify and categorize the error
4. Demonstrates the repair cycle logic

This is a demonstration script, not a pytest test.
"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from state_machine import SelfHealingStateMachine, State


def demo_auto_fixable_error():
    """Demonstrate auto-fixable error workflow"""
    print("\n" + "="*60)
    print("DEMO 1: Auto-Fixable Error (AssertionError)")
    print("="*60)
    
    machine = SelfHealingStateMachine(limit=3)
    
    # Simulate pytest report with AssertionError
    error_message = """
    def test_calculate_sum():
        result = calculate_sum(5, 3)
>       assert result == 8
E       AssertionError: assert 7 == 8
    """
    
    print("\n1. Identifying error...")
    state = machine.identify_error(error_message)
    print(f"   ✓ Error identified: {machine.error_type}")
    print(f"   ✓ State: {state.value}")
    
    print("\n2. Checking if repair can be attempted...")
    can_repair = machine.can_attempt_repair()
    print(f"   ✓ Can attempt repair: {can_repair}")
    
    print("\n3. Simulating repair attempts...")
    
    # Attempt 1: Fails
    print("\n   Attempt 1/3: Applying fix...")
    print("   ❌ Pytest failed after fix")
    machine.record_repair_attempt(success=False)
    print(f"   Counter: {machine.counter}/{machine.limit}")
    
    # Attempt 2: Succeeds
    print("\n   Attempt 2/3: Applying improved fix...")
    print("   ✅ Pytest passed!")
    machine.record_repair_attempt(success=True)
    
    print(f"\n4. Final state: {machine.state.value}")
    print(f"\n{machine.get_final_message()}")
    
    return machine.state == State.SUCCESS


def demo_infrastructure_error():
    """Demonstrate infrastructure error workflow"""
    print("\n" + "="*60)
    print("DEMO 2: Infrastructure Error (Timeout)")
    print("="*60)
    
    machine = SelfHealingStateMachine(limit=3)
    
    # Simulate pytest report with TimeoutError
    error_message = """
    def test_api_call():
        response = requests.get('https://api.example.com/data')
>       assert response.status_code == 200
E       TimeoutError: Connection timed out after 30 seconds
    """
    
    print("\n1. Identifying error...")
    state = machine.identify_error(error_message)
    print(f"   ✓ Error type detected: {machine.error_type}")
    print(f"   ✓ State: {state.value}")
    print(f"   ✓ Reason: {machine.failure_reason.value if machine.failure_reason else 'N/A'}")
    
    print("\n2. Checking if repair can be attempted...")
    can_repair = machine.can_attempt_repair()
    print(f"   ✗ Can attempt repair: {can_repair}")
    print("   → Infrastructure errors require human intervention")
    
    print("\n3. Checking if human notification is needed...")
    notify = machine.should_notify_human()
    print(f"   ✓ Notify human: {notify}")
    
    print(f"\n{machine.get_final_message()}")
    
    return machine.state == State.NEEDS_HUMAN


def demo_failed_limit():
    """Demonstrate failed limit workflow"""
    print("\n" + "="*60)
    print("DEMO 3: Failed Limit (Max Attempts Reached)")
    print("="*60)
    
    machine = SelfHealingStateMachine(limit=3)
    
    # Simulate pytest report with SyntaxError
    error_message = """
    def test_function():
>       result = broken_function()
E       SyntaxError: invalid syntax in broken_function
    """
    
    print("\n1. Identifying error...")
    state = machine.identify_error(error_message)
    print(f"   ✓ Error identified: {machine.error_type}")
    print(f"   ✓ State: {state.value}")
    
    print("\n2. Simulating repair cycle...")
    
    for i in range(3):
        print(f"\n   Attempt {i+1}/3: Applying fix...")
        print(f"   ❌ Pytest still failing")
        machine.record_repair_attempt(success=False)
        print(f"   Counter: {machine.counter}/{machine.limit}")
        
        if machine.state == State.FAILED_LIMIT:
            print("\n   ⚠️  Maximum attempts reached!")
            break
    
    print(f"\n3. Final state: {machine.state.value}")
    print(f"\n{machine.get_final_message()}")
    
    return machine.state == State.FAILED_LIMIT


def demo_unknown_error():
    """Demonstrate unknown error workflow"""
    print("\n" + "="*60)
    print("DEMO 4: Unknown Error Type")
    print("="*60)
    
    machine = SelfHealingStateMachine(limit=3)
    
    # Simulate pytest report with unknown error
    error_message = """
    def test_custom_logic():
>       result = custom_processor()
E       CustomBusinessError: Invalid state transition from PENDING to COMPLETED
    """
    
    print("\n1. Identifying error...")
    state = machine.identify_error(error_message)
    print(f"   ✓ State: {state.value}")
    print(f"   ✓ Reason: {machine.failure_reason.value if machine.failure_reason else 'N/A'}")
    
    print("\n2. Checking if repair can be attempted...")
    can_repair = machine.can_attempt_repair()
    print(f"   ✗ Can attempt repair: {can_repair}")
    print("   → Unknown errors require human analysis")
    
    print(f"\n{machine.get_final_message()}")
    
    return machine.state == State.NEEDS_HUMAN


def demo_status_reporting():
    """Demonstrate status reporting"""
    print("\n" + "="*60)
    print("DEMO 5: Status Reporting")
    print("="*60)
    
    machine = SelfHealingStateMachine(limit=3)
    machine.identify_error("NameError: name 'user' is not defined")
    
    print("\nMachine Status:")
    status = machine.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    print("\nAfter first failed attempt:")
    machine.record_repair_attempt(success=False)
    status = machine.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    return True


def main():
    """Run all demonstrations"""
    print("\n" + "="*60)
    print("SELF-HEALING STATE MACHINE - INTEGRATION DEMO")
    print("="*60)
    print("\nThis demo shows how the state machine handles different")
    print("error types and manages the repair cycle.")
    
    demos = [
        ("Auto-Fixable Error", demo_auto_fixable_error),
        ("Infrastructure Error", demo_infrastructure_error),
        ("Failed Limit", demo_failed_limit),
        ("Unknown Error", demo_unknown_error),
        ("Status Reporting", demo_status_reporting),
    ]
    
    results = []
    
    for name, demo_func in demos:
        try:
            success = demo_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ Demo failed with error: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("DEMO SUMMARY")
    print("="*60)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(success for _, success in results)
    
    if all_passed:
        print("\n✅ All demonstrations completed successfully!")
        print("\nThe state machine is working as expected:")
        print("  • Auto-fixable errors → CHANGE_REQUESTED → repair cycle")
        print("  • Infrastructure errors → NEEDS_HUMAN (Falha de Infra)")
        print("  • Unknown errors → NEEDS_HUMAN (Erro não identificado)")
        print("  • Failed repairs → FAILED_LIMIT after 3 attempts")
        return 0
    else:
        print("\n❌ Some demonstrations failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
