#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Demo script for Jarvis Task Executor

This script demonstrates the capabilities of the Task Executor system:
1. TaskRunner - Ephemeral script execution with dependency management
2. PersistentBrowserManager - Browser automation with persistent sessions
3. Mission payload structure and execution
"""

import logging
from pathlib import Path

from app.application.services.browser_manager import PersistentBrowserManager
from app.application.services.task_runner import TaskRunner
from app.domain.models.mission import Mission

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def demo_simple_execution():
    """Demo 1: Simple script execution without dependencies"""
    logger.info("\n" + "=" * 60)
    logger.info("DEMO 1: Simple Script Execution")
    logger.info("=" * 60)

    # Create TaskRunner
    task_runner = TaskRunner(use_venv=False)

    # Create a simple mission
    mission = Mission(
        mission_id="demo_001",
        code="""
import sys
print(f"Python version: {sys.version}")
print("Hello from Jarvis Task Executor!")
result = 2 + 2
print(f"2 + 2 = {result}")
""",
        requirements=[],
        browser_interaction=False,
        keep_alive=False,
    )

    # Execute the mission
    logger.info("Executing simple mission...")
    result = task_runner.execute_mission(mission)

    # Display results
    logger.info(f"Mission: {result.mission_id}")
    logger.info(f"Success: {result.success}")
    logger.info(f"Exit Code: {result.exit_code}")
    logger.info(f"Execution Time: {result.execution_time:.2f}s")
    logger.info(f"\nOutput:\n{result.stdout}")
    if result.stderr:
        logger.warning(f"Errors:\n{result.stderr}")


def demo_with_dependencies():
    """Demo 2: Script execution with package dependencies"""
    logger.info("\n" + "=" * 60)
    logger.info("DEMO 2: Script with Dependencies")
    logger.info("=" * 60)

    # Create TaskRunner
    task_runner = TaskRunner(use_venv=False)

    # Create a mission that uses external packages
    mission = Mission(
        mission_id="demo_002",
        code="""
# Example: Using requests to fetch data from an API
import json

# Simple example without actually making HTTP request
# In real scenario, you would do: response = requests.get('https://api.github.com')
data = {
    "status": "success",
    "message": "This would normally fetch data from an API",
    "example": "GitHub API request"
}

print(json.dumps(data, indent=2))
""",
        requirements=[],  # Would be ["requests"] in real scenario
        browser_interaction=False,
        keep_alive=False,
        timeout=60,
    )

    # Execute the mission
    logger.info("Executing mission with dependencies...")
    result = task_runner.execute_mission(mission)

    # Display results
    logger.info(f"Mission: {result.mission_id}")
    logger.info(f"Success: {result.success}")
    logger.info(f"Execution Time: {result.execution_time:.2f}s")
    logger.info(f"\nOutput:\n{result.stdout}")


def demo_error_handling():
    """Demo 3: Error handling in task execution"""
    logger.info("\n" + "=" * 60)
    logger.info("DEMO 3: Error Handling")
    logger.info("=" * 60)

    # Create TaskRunner
    task_runner = TaskRunner(use_venv=False)

    # Create a mission that will fail
    mission = Mission(
        mission_id="demo_003",
        code="""
# This script will raise an error
print("Starting execution...")
raise ValueError("This is a demonstration error")
print("This line will never execute")
""",
        requirements=[],
        browser_interaction=False,
        keep_alive=False,
    )

    # Execute the mission
    logger.info("Executing mission with intentional error...")
    result = task_runner.execute_mission(mission)

    # Display results
    logger.info(f"Mission: {result.mission_id}")
    logger.info(f"Success: {result.success}")
    logger.info(f"Exit Code: {result.exit_code}")
    logger.info(f"\nStdout:\n{result.stdout}")
    logger.info(f"Stderr:\n{result.stderr}")
    if result.error:
        logger.info(f"Error: {result.error}")


def demo_timeout():
    """Demo 4: Mission timeout handling"""
    logger.info("\n" + "=" * 60)
    logger.info("DEMO 4: Timeout Handling")
    logger.info("=" * 60)

    # Create TaskRunner
    task_runner = TaskRunner(use_venv=False)

    # Create a mission with a short timeout
    mission = Mission(
        mission_id="demo_004",
        code="""
import time
print("Starting long-running task...")
for i in range(10):
    print(f"Step {i+1}/10")
    time.sleep(1)
print("Task completed!")
""",
        requirements=[],
        browser_interaction=False,
        keep_alive=False,
        timeout=3,  # 3 second timeout
    )

    # Execute the mission
    logger.info("Executing mission with 3 second timeout...")
    result = task_runner.execute_mission(mission)

    # Display results
    logger.info(f"Mission: {result.mission_id}")
    logger.info(f"Success: {result.success}")
    logger.info(f"Exit Code: {result.exit_code}")
    logger.info(f"Execution Time: {result.execution_time:.2f}s")
    logger.info(f"\nPartial Output:\n{result.stdout}")


def demo_browser_manager():
    """Demo 5: Browser manager initialization"""
    logger.info("\n" + "=" * 60)
    logger.info("DEMO 5: Browser Manager")
    logger.info("=" * 60)

    # Create browser manager
    browser_manager = PersistentBrowserManager(
        headless=True,
        browser_type="chromium"
    )

    logger.info(f"Browser Manager initialized")
    logger.info(f"User Data Directory: {browser_manager.user_data_dir}")
    logger.info(f"Headless Mode: {browser_manager.headless}")
    logger.info(f"Browser Type: {browser_manager.browser_type}")

    # Check browser status
    is_running = browser_manager.is_running()
    logger.info(f"Browser Running: {is_running}")

    logger.info("\nNote: To actually start the browser, Playwright must be installed:")
    logger.info("  pip install playwright")
    logger.info("  playwright install chromium")


def demo_mission_serialization():
    """Demo 6: Mission serialization to/from JSON"""
    logger.info("\n" + "=" * 60)
    logger.info("DEMO 6: Mission Serialization")
    logger.info("=" * 60)

    # Create a mission
    mission = Mission(
        mission_id="demo_006",
        code="print('Hello, World!')",
        requirements=["requests", "beautifulsoup4"],
        browser_interaction=True,
        keep_alive=False,
        target_device_id=123,
        timeout=120,
        metadata={"source": "demo", "priority": "high"},
    )

    # Convert to dictionary
    mission_dict = mission.to_dict()
    logger.info("Mission as dictionary:")
    import json
    logger.info(json.dumps(mission_dict, indent=2))

    # Convert back to Mission
    restored_mission = Mission.from_dict(mission_dict)
    logger.info(f"\nRestored mission ID: {restored_mission.mission_id}")
    logger.info(f"Requirements: {restored_mission.requirements}")
    logger.info(f"Browser interaction: {restored_mission.browser_interaction}")


def main():
    """Run all demos"""
    logger.info("Starting Jarvis Task Executor Demo")
    logger.info("=" * 60)

    try:
        # Run demos
        demo_simple_execution()
        demo_with_dependencies()
        demo_error_handling()
        demo_timeout()
        demo_browser_manager()
        demo_mission_serialization()

        logger.info("\n" + "=" * 60)
        logger.info("All demos completed!")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("\nDemo interrupted by user")
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
