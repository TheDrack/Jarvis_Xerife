from app.core.nexus import nexus
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
        """Delegate to the single blueprint generator (ADR-006 R3)."""
        from app.application.services.capability_blueprint_service import (
            generate_capability_blueprint,
        )

        return generate_capability_blueprint(capability)

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
            github_adapter = nexus.resolve("github_adapter")
        
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
