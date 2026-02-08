#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Demo: Self-Healing Orchestrator

This script demonstrates the key features of Jarvis's Self-Healing Orchestrator:
1. ThoughtLog creation and retrieval
2. Retry counting and escalation
3. GitHub worker operations
4. Auto-healing workflow
"""

import json
from datetime import datetime
from sqlmodel import Session, SQLModel, create_engine

from app.domain.models.thought_log import InteractionStatus, ThoughtLog
from app.application.services.thought_log_service import ThoughtLogService
from app.application.services.github_worker import GitHubWorker


def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def demo_thought_log_service():
    """Demonstrate ThoughtLog service functionality"""
    print_section("1. ThoughtLog Service Demo")
    
    # Create in-memory database
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    service = ThoughtLogService(engine=engine)
    
    mission_id = "demo_ci_fix_001"
    session_id = "demo_session_001"
    
    print(f"\n📝 Creating thought logs for mission: {mission_id}")
    
    # Attempt 1 - Failed
    print("\n  Attempt 1: Analyzing CI failure...")
    thought1 = service.create_thought(
        mission_id=mission_id,
        session_id=session_id,
        thought_process="Analyzing CI logs. Found ImportError: numpy not found",
        problem_description="CI build failed with missing dependency",
        solution_attempt="Adding numpy==1.24.0 to requirements.txt",
        status=InteractionStatus.INTERNAL_MONOLOGUE,
        success=False,
        error_message="Still failing - version conflict with pandas",
        context_data={"error_type": "ImportError", "module": "numpy"}
    )
    print(f"    ✗ Failed (retry_count: {thought1.retry_count})")
    
    # Attempt 2 - Failed
    print("\n  Attempt 2: Fixing version conflict...")
    thought2 = service.create_thought(
        mission_id=mission_id,
        session_id=session_id,
        thought_process="Version conflict detected. Updating pandas to 2.0.0",
        problem_description="CI build failed with version conflict",
        solution_attempt="Updated pandas==2.0.0 for compatibility",
        status=InteractionStatus.INTERNAL_MONOLOGUE,
        success=False,
        error_message="New error in scipy compatibility",
        context_data={"error_type": "VersionConflict"}
    )
    print(f"    ✗ Failed (retry_count: {thought2.retry_count})")
    
    # Attempt 3 - Failed
    print("\n  Attempt 3: Regenerating dependencies...")
    thought3 = service.create_thought(
        mission_id=mission_id,
        session_id=session_id,
        thought_process="Multiple conflicts. Regenerating entire dependency tree",
        problem_description="CI build failed with complex dependency conflicts",
        solution_attempt="Regenerated requirements.txt from pip freeze",
        status=InteractionStatus.INTERNAL_MONOLOGUE,
        success=False,
        error_message="Still failing - issue persists",
        context_data={"strategy": "full_regeneration"}
    )
    print(f"    ✗ Failed (retry_count: {thought3.retry_count})")
    
    # Attempt 4 - Triggers escalation
    print("\n  Attempt 4: Escalation triggered...")
    thought4 = service.create_thought(
        mission_id=mission_id,
        session_id=session_id,
        thought_process="All automated attempts failed. Need human review",
        problem_description="CI build failed - unable to auto-resolve",
        solution_attempt="Escalating to Commander for manual intervention",
        status=InteractionStatus.INTERNAL_MONOLOGUE,
        success=False,
        error_message="Maximum retries exceeded",
        context_data={"escalation_trigger": "max_retries"}
    )
    print(f"    🚨 ESCALATED (retry_count: {thought4.retry_count})")
    print(f"    requires_human: {thought4.requires_human}")
    print(f"    escalation_reason: {thought4.escalation_reason}")
    
    # Show all thoughts for mission
    print("\n\n📋 All thoughts for mission:")
    thoughts = service.get_mission_thoughts(mission_id)
    for i, thought in enumerate(thoughts, 1):
        status_icon = "✓" if thought.success else "✗"
        print(f"  {i}. [{status_icon}] Retry {thought.retry_count}: {thought.solution_attempt[:50]}...")
    
    # Show consolidated log
    print("\n\n📝 Consolidated Log:")
    consolidated = service.generate_consolidated_log(mission_id)
    print(consolidated)
    
    # Check escalations
    print("\n\n🚨 Pending Escalations:")
    escalations = service.get_pending_escalations()
    print(f"  Total pending: {len(escalations)}")
    for escalation in escalations:
        print(f"  - Mission {escalation.mission_id}: {escalation.escalation_reason}")


def demo_github_worker():
    """Demonstrate GitHub worker functionality"""
    print_section("2. GitHub Worker Demo")
    
    worker = GitHubWorker()
    
    print("\n🔧 GitHub CLI Status:")
    is_available = worker._check_gh_cli()
    print(f"  GitHub CLI available: {is_available}")
    
    if not is_available:
        print("\n  ℹ️  To use GitHub worker features, install gh CLI:")
        print("     https://cli.github.com/")
        print("     Then run: gh auth login")
        return
    
    print("\n📝 Example Operations:")
    print("\n  1. Create Feature Branch:")
    print('     worker.create_feature_branch("feature/auto-fix-ci-123")')
    
    print("\n  2. Submit Pull Request:")
    print('     worker.submit_pull_request(')
    print('         title="Auto-fix: Resolve CI dependency conflict",')
    print('         body="This PR was auto-generated by Jarvis"')
    print('     )')
    
    print("\n  3. Check CI Status:")
    print('     worker.fetch_ci_status(run_id=12345)')
    
    print("\n  4. Download CI Logs:")
    print('     worker.download_ci_logs(run_id=12345)')
    
    print("\n  5. Apply Patch:")
    print('     worker.file_write("requirements.txt", new_content)')


def demo_auto_healing_workflow():
    """Demonstrate the complete auto-healing workflow"""
    print_section("3. Auto-Healing Workflow Demo")
    
    print("\n🔄 Complete Self-Healing Cycle:\n")
    
    steps = [
        "1. CI Failure Detection",
        "   └─ GitHub Actions workflow fails",
        "",
        "2. Auto-Heal Trigger",
        "   └─ POST /v1/github/ci-heal/{run_id}",
        "",
        "3. Log Analysis",
        "   └─ Download logs via: gh run view --log",
        "   └─ Parse error messages and stack traces",
        "",
        "4. Internal Reasoning (INTERNAL_MONOLOGUE)",
        "   └─ Create ThoughtLog with analysis",
        "   └─ Identify root cause",
        "   └─ Generate solution strategy",
        "",
        "5. Solution Application",
        "   └─ Generate code fix or config update",
        "   └─ Apply via file_write()",
        "",
        "6. Commit & Push",
        "   └─ create_feature_branch()",
        "   └─ submit_pull_request()",
        "",
        "7. Retry",
        "   └─ New CI run triggered automatically",
        "   └─ Monitor status",
        "",
        "8. Safety Latch Check",
        "   ├─ If retry_count < 3: Continue to step 3",
        "   └─ If retry_count >= 3: Escalate to Human",
        "",
        "9. Human Escalation (if needed)",
        "   └─ Generate consolidated log",
        "   └─ POST to /v1/thoughts/escalations",
        "   └─ Notify Commander",
    ]
    
    for step in steps:
        print(f"  {step}")
    
    print("\n\n💡 Key Features:")
    features = [
        "✓ Automatic retry with exponential backoff",
        "✓ Three-strike safety mechanism",
        "✓ Persistent thought logging",
        "✓ Human-in-the-loop escalation",
        "✓ Consolidated debugging logs",
        "✓ Full GitHub integration",
    ]
    
    for feature in features:
        print(f"  {feature}")


def demo_api_integration():
    """Show API integration examples"""
    print_section("4. API Integration Example")
    
    print("\n📡 Python Client Example:\n")
    
    code = '''
import requests

class JarvisSelfHealing:
    def __init__(self, api_base_url, token):
        self.base_url = api_base_url
        self.headers = {"Authorization": f"Bearer {token}"}
    
    def create_thought_log(self, mission_id, thought_data):
        """Create a new thought log entry"""
        response = requests.post(
            f"{self.base_url}/v1/thoughts",
            json={
                "mission_id": mission_id,
                "session_id": thought_data["session_id"],
                "status": "internal_monologue",
                "thought_process": thought_data["process"],
                "problem_description": thought_data["problem"],
                "solution_attempt": thought_data["solution"],
                "success": thought_data["success"],
                "error_message": thought_data.get("error", ""),
                "context_data": thought_data.get("context", {})
            },
            headers=self.headers
        )
        return response.json()
    
    def get_mission_status(self, mission_id):
        """Check if mission requires human intervention"""
        response = requests.get(
            f"{self.base_url}/v1/thoughts/mission/{mission_id}",
            headers=self.headers
        )
        
        data = response.json()
        latest = data["logs"][-1] if data["logs"] else None
        
        if latest and latest["requires_human"]:
            # Get consolidated log
            log_response = requests.get(
                f"{self.base_url}/v1/thoughts/mission/{mission_id}/consolidated",
                headers=self.headers
            )
            return {
                "status": "ESCALATED",
                "consolidated_log": log_response.json()["consolidated_log"]
            }
        
        return {"status": "IN_PROGRESS", "attempts": len(data["logs"])}
    
    def auto_heal_ci(self, run_id, mission_id):
        """Trigger auto-healing for a CI failure"""
        response = requests.post(
            f"{self.base_url}/v1/github/ci-heal/{run_id}",
            params={"mission_id": mission_id},
            headers=self.headers
        )
        return response.json()

# Usage
jarvis = JarvisSelfHealing("http://localhost:8000", "your-token")

# Monitor CI and auto-heal
result = jarvis.auto_heal_ci(run_id=12345, mission_id="fix_build_123")

if result.get("requires_human"):
    print("🚨 Escalated to human")
    print(result["consolidated_log"])
else:
    print("✅ Auto-heal successful")
'''
    
    print(code)


def main():
    """Run all demos"""
    print("\n" + "="*60)
    print("  JARVIS SELF-HEALING ORCHESTRATOR DEMO")
    print("="*60)
    print("\nDemonstrating Jarvis's self-evolution architecture")
    
    # Run demos
    demo_thought_log_service()
    demo_github_worker()
    demo_auto_healing_workflow()
    demo_api_integration()
    
    print("\n" + "="*60)
    print("  Demo Complete!")
    print("="*60)
    print("\n📚 For more information, see:")
    print("  - API_README.md")
    print("  - SELF_HEALING_ARCHITECTURE.md")
    print("\n")


if __name__ == "__main__":
    main()
