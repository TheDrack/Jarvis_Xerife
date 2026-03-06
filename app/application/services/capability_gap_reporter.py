from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Capability Gap Reporter - Reports capability gaps via Pull Requests"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.domain.models.capability import JarvisCapability

logger = logging.getLogger(__name__)


class CapabilityGapReporter(NexusComponent):
    def execute(self, context: dict) -> dict:
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    def __init__(self, engine):
        """
        Initialize the Capability Gap Reporter

        Args:
            engine: SQLAlchemy engine for database operations
        """
        self.engine = engine

    def _generate_blueprint(self, capability: JarvisCapability) -> Dict[str, Any]:
        """
        Generate a technical blueprint for implementing a capability.
        
        This is where AI could be used to analyze the capability name/description
        and generate technical requirements. For now, we use rule-based logic.
        """
        blueprint = {
            "capability_id": capability.id,
            "capability_name": capability.capability_name,
            "chapter": capability.chapter,
            "status": capability.status,
            "requirements": [],
            "libraries": [],
            "apis": [],
            "env_vars": [],
            "permissions": [],
            "blueprint": ""
        }
        
        # Rule-based blueprint generation based on capability patterns
        name_lower = capability.capability_name.lower()
        
        # Memory-related capabilities
        if "memory" in name_lower:
            blueprint["libraries"].extend(["redis", "sqlalchemy"])
            blueprint["requirements"].append("Persistent storage system")
            blueprint["blueprint"] = "Implement using Redis for short-term cache and PostgreSQL for long-term storage"
        
        # Learning-related capabilities
        if "learn" in name_lower:
            blueprint["libraries"].extend(["scikit-learn", "numpy"])
            blueprint["requirements"].append("Machine learning framework")
            blueprint["blueprint"] = "Implement feedback loop with ML model training"
        
        # Economic/cost capabilities
        if "cost" in name_lower or "economic" in name_lower or "revenue" in name_lower:
            blueprint["libraries"].append("stripe")
            blueprint["apis"].append("Stripe API")
            blueprint["env_vars"].append("STRIPE_API_KEY")
            blueprint["requirements"].append("Payment processing system")
            blueprint["blueprint"] = "Integrate with Stripe for payment tracking and processing"
        
        # Monitoring/detection capabilities
        if "detect" in name_lower or "monitor" in name_lower:
            blueprint["libraries"].extend(["prometheus-client", "sentry-sdk"])
            blueprint["requirements"].append("Monitoring and alerting system")
            blueprint["blueprint"] = "Implement with Prometheus metrics and Sentry error tracking"
        
        # Testing capabilities
        if "test" in name_lower or "validate" in name_lower:
            blueprint["libraries"].extend(["pytest", "hypothesis"])
            blueprint["requirements"].append("Automated testing framework")
            blueprint["blueprint"] = "Extend pytest suite with property-based testing"
        
        # Strategic/planning capabilities
        if "plan" in name_lower or "strateg" in name_lower:
            blueprint["requirements"].append("Advanced LLM integration")
            blueprint["env_vars"].extend(["OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
            blueprint["blueprint"] = "Use LLM chain-of-thought for multi-step planning"
        
        # Orchestration capabilities
        if "orchestrat" in name_lower or "parallel" in name_lower or "distribut" in name_lower:
            blueprint["libraries"].extend(["celery", "redis"])
            blueprint["requirements"].append("Distributed task queue")
            blueprint["blueprint"] = "Implement with Celery for distributed task execution"
        
        return blueprint

    async def report_capability_gap_via_pr(
        self,
        capability_id: int,
        github_adapter=None
    ) -> Dict[str, Any]:
        """
        Report a capability gap by creating a Pull Request instead of an Issue.
        
        This is the new protocol - when a test failure or capability gap is detected,
        we create a PR with autonomous_instruction.json that triggers the Jarvis
        Autonomous State Machine workflow.
        
        Flow:
        1. Detect Gap -> Generate Blueprint
        2. Create Branch (auto-fix/capability-{id}-{timestamp})
        3. Create autonomous_instruction.json with capability details
        4. Open Pull Request with Copilot Workspace fallback link
        
        Args:
            capability_id: ID of the capability with a gap
            github_adapter: Optional GitHubAdapter instance.
                If not provided, will create one.
        
        Returns:
            Dictionary with 'success' boolean and PR details or error message
        
        Example:
            >>> reporter = CapabilityGapReporter(engine)
            >>> result = await reporter.report_capability_gap_via_pr(capability_id=42)
        """
        # Get capability details
        with Session(self.engine) as session:
            capability = session.get(JarvisCapability, capability_id)
            if not capability:
                return {
                    "success": False,
                    "error": f"Capability {capability_id} not found"
                }

            # Generate blueprint for the capability
            blueprint = self._generate_blueprint(capability)
        
        # Lazy import to avoid circular dependency
        if github_adapter is None:
            from app.adapters.infrastructure.github_adapter import GitHubAdapter
            github_adapter = GitHubAdapter()
        
        # Prepare structured description for autonomous_instruction.json
        libs = '\n'.join(f"- {lib}" for lib in blueprint.get('libraries', [])) or '- None'
        apis = '\n'.join(f"- {api}" for api in blueprint.get('apis', [])) or '- None'
        envs = '\n'.join(f"- {env}" for env in blueprint.get('env_vars', [])) or '- None'
        perms = '\n'.join(f"- {perm}" for perm in blueprint.get('permissions', [])) or '- None'
        reqs = '\n'.join(f"- {req}" for req in blueprint.get('requirements', [])) or '- None'

        description = f"""# Capability Gap Detected

**Capability ID**: {capability.id}
**Capability Name**: {capability.capability_name}
**Chapter**: {capability.chapter}
**Current Status**: {capability.status}

## Blueprint for Implementation

{blueprint.get('blueprint', 'No blueprint available')}

## Technical Requirements

### Libraries Needed
{libs}

### APIs Required
{apis}

### Environment Variables
{envs}

### Permissions
{perms}

## Requirements Summary
{reqs}

---
**Note**: This is an automated capability gap report.
The system has detected that this capability is not yet implemented
and requires attention.
"""
        
        # Use report_for_auto_correction to create the PR
        title = f"Implement Capability: {capability.capability_name}"
        
        logger.info(f"Creating PR for capability gap: {capability.capability_name}")
        
        result = await github_adapter.report_for_auto_correction(
            title=title,
            description=description,
            improvement_context=(
                f"Capability {capability.id} needs implementation "
                f"to advance JARVIS evolution."
            )
        )
        
        return result
