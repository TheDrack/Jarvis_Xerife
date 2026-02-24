#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example: Evolution Loop Integration

This script demonstrates how to integrate the Evolution Loop Service
into your deployment pipeline and test runs.

Usage scenarios:
1. Called from CI/CD after pytest runs
2. Called after successful/failed deployments
3. Integrated into the HUD login flow
4. Used with cron jobs for periodic analysis
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
from app.adapters.infrastructure.reward_adapter import RewardAdapter
from app.application.services.evolution_loop import EvolutionLoopService
from app.core.config import settings


def example_pytest_integration():
    """
    Example: Log pytest results

    This would typically be called from a CI/CD pipeline or
    pytest hook after test execution.
    """
    print("\n=== Example 1: Pytest Integration ===\n")

    # Initialize services
    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
    reward_adapter = RewardAdapter(engine=db_adapter.engine)
    evolution_service = EvolutionLoopService(reward_provider=reward_adapter)

    # Simulate test results
    print("Running pytest...")

    # Example 1: All tests passed
    reward_id = evolution_service.log_pytest_result(
        passed=True,
        test_count=25,
        metadata={'ci_run_id': 'example-123', 'branch': 'main'}
    )
    print(f"✅ Logged positive reward for passing tests (ID: {reward_id})")

    # Example 2: Some tests failed
    reward_id = evolution_service.log_pytest_result(
        passed=False,
        test_count=25,
        failed_tests=[
            'tests/test_example.py::test_feature_x',
            'tests/test_integration.py::test_api_call'
        ],
        metadata={'ci_run_id': 'example-124', 'branch': 'feature/new-thing'}
    )
    print(f"❌ Logged negative reward for failed tests (ID: {reward_id})")


def example_deployment_integration():
    """
    Example: Log deployment results

    This would typically be called from deployment scripts
    (e.g., render.yaml, GitHub Actions, etc.)
    """
    print("\n=== Example 2: Deployment Integration ===\n")

    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
    reward_adapter = RewardAdapter(engine=db_adapter.engine)
    evolution_service = EvolutionLoopService(reward_provider=reward_adapter)

    # Example 1: Successful deployment
    print("Deploying to production...")
    reward_id = evolution_service.log_deploy_result(
        success=True,
        deployment_id='deploy-prod-456',
        metadata={'environment': 'production', 'version': '1.2.3'}
    )
    print(f"✅ Logged positive reward for successful deployment (ID: {reward_id})")

    # Example 2: Failed deployment
    print("\nDeploying to staging...")
    reward_id = evolution_service.log_deploy_result(
        success=False,
        error_message='Build failed: Missing dependency xyz',
        deployment_id='deploy-staging-789',
        metadata={'environment': 'staging', 'version': '1.3.0-beta'}
    )
    print(f"❌ Logged negative reward for failed deployment (ID: {reward_id})")

    # Example 3: Rollback scenario
    print("\nRolling back due to critical error...")
    reward_id = evolution_service.log_deploy_result(
        success=False,
        rollback=True,
        deployment_id='rollback-prod-999',
        error_message='Critical bug in production, rolling back',
        metadata={'environment': 'production', 'rollback_from': '1.2.3', 'rollback_to': '1.2.2'}
    )
    print(f"🔄 Logged negative reward for rollback (ID: {reward_id})")


def example_roadmap_progress():
    """
    Example: Log roadmap progress

    This would be called when capability status changes or
    roadmap completion percentage increases.
    """
    print("\n=== Example 3: Roadmap Progress ===\n")

    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
    reward_adapter = RewardAdapter(engine=db_adapter.engine)
    evolution_service = EvolutionLoopService(reward_provider=reward_adapter)

    # Example 1: Roadmap progress increase
    print("Roadmap completion increased by 2.5%...")
    reward_id = evolution_service.log_roadmap_progress(
        progress_percentage=2.5,
        chapter='CHAPTER_3_ADVANCED_CAPABILITIES',
        metadata={'previous_progress': 45.0, 'new_progress': 47.5}
    )
    print(f"📈 Logged reward for roadmap progress (ID: {reward_id})")

    # Example 2: Capability completion
    print("\nCapability completed: Voice Recognition...")
    reward_id = evolution_service.log_capability_update(
        capability_name='Voice Recognition with Wake Word',
        old_status='partial',
        new_status='complete',
        metadata={'chapter': 'CHAPTER_1', 'capability_id': 5}
    )
    print(f"🎯 Logged reward for capability completion (ID: {reward_id})")


def example_hud_login_status():
    """
    Example: Display status on HUD login

    This would be called when a user logs into the HUD
    to show their current efficiency status.
    """
    print("\n=== Example 4: HUD Login Status ===\n")

    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
    reward_adapter = RewardAdapter(engine=db_adapter.engine)
    evolution_service = EvolutionLoopService(reward_provider=reward_adapter)

    print("User logged into HUD...")

    # Get evolution status
    status = evolution_service.get_evolution_status(days=7)

    # Display commander message
    print(f"\n{status['commander_message']}\n")

    # Display key metrics
    print(f"📊 Efficiency Score: {status['efficiency_score']:+.1f} pontos")
    print(f"📈 Improvement: {status['improvement']:+.1f} pontos ({status['improvement_percentage']:+.1f}%)")
    print(f"✅ Success Rate: {status['success_rate']:.1f}%")
    print(f"🎯 Total Actions: {status['total_actions']}")


def example_policy_engine_analysis():
    """
    Example: Using the Policy Engine for analysis

    This demonstrates using Llama 3.3-70b to analyze
    past performance and recommend improvements.

    Note: Requires AI Gateway to be configured.
    """
    print("\n=== Example 5: Policy Engine Analysis ===\n")

    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
    reward_adapter = RewardAdapter(engine=db_adapter.engine)

    # Note: In real usage, you would pass the ai_gateway instance
    # evolution_service = EvolutionLoopService(
    #     reward_provider=reward_adapter,
    #     ai_gateway=ai_gateway_instance
    # )
    evolution_service = EvolutionLoopService(reward_provider=reward_adapter)

    print("Policy Engine would analyze:")
    print("- Past 30 days of reward history")
    print("- Success/failure patterns")
    print("- Recommend safest path for next goal")
    print("\nNote: Requires AI Gateway configuration and async execution")
    print("Example async call:")
    print("  analysis = await evolution_service.analyze_with_policy_engine(days=30)")
    print("  print(analysis['analysis'])")


def main():
    """Run all examples."""
    print("=" * 70)
    print("    JARVIS EVOLUTION LOOP - Integration Examples")
    print("=" * 70)

    try:
        example_pytest_integration()
        example_deployment_integration()
        example_roadmap_progress()
        example_hud_login_status()
        example_policy_engine_analysis()

        print("\n" + "=" * 70)
        print("All examples completed successfully!")
        print("=" * 70 + "\n")

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
