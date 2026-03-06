from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Capability Blueprint Service - blueprint generation and resource validation.

Extracted from CapabilityManager to keep file sizes manageable.
Provides check_requirements(), _generate_blueprint(), and resource_request().
"""

import logging
import os
from typing import Any, Dict, List, Optional

from sqlmodel import Session
from sqlalchemy.engine import Engine

from app.domain.models.capability import JarvisCapability

logger = logging.getLogger(__name__)


class CapabilityBlueprintService(NexusComponent):
    """Generates technical blueprints and validates resource requirements for capabilities."""

    def execute(self, context: dict) -> dict:
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def check_requirements(self, capability_id: int) -> Dict[str, Any]:
        """Generate a technical blueprint for a capability.

        Args:
            capability_id: The ID of the capability to check

        Returns:
            Dictionary containing requirements, libraries, apis, env_vars, permissions, blueprint.
        """
        with Session(self.engine) as session:
            capability = session.get(JarvisCapability, capability_id)
            if not capability:
                return {"error": f"Capability {capability_id} not found"}
            return self._generate_blueprint(capability)

    def _generate_blueprint(self, capability: JarvisCapability) -> Dict[str, Any]:
        """Generate a technical blueprint for implementing a capability using rule-based logic."""
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
            "blueprint": "",
        }

        name_lower = capability.capability_name.lower()

        if "memory" in name_lower:
            blueprint["libraries"].extend(["redis", "sqlalchemy"])
            blueprint["requirements"].append("Persistent storage system")
            blueprint["blueprint"] = (
                "Implement using Redis for short-term cache and PostgreSQL for long-term storage"
            )

        if "learn" in name_lower:
            blueprint["libraries"].extend(["scikit-learn", "numpy"])
            blueprint["requirements"].append("Machine learning framework")
            blueprint["blueprint"] = "Implement feedback loop with ML model training"

        if "cost" in name_lower or "economic" in name_lower or "revenue" in name_lower:
            blueprint["libraries"].append("stripe")
            blueprint["apis"].append("Stripe API")
            blueprint["env_vars"].append("STRIPE_API_KEY")
            blueprint["requirements"].append("Payment processing system")
            blueprint["blueprint"] = "Integrate with Stripe for payment tracking and processing"

        if "detect" in name_lower or "monitor" in name_lower:
            blueprint["libraries"].extend(["prometheus-client", "sentry-sdk"])
            blueprint["requirements"].append("Monitoring and alerting system")
            blueprint["blueprint"] = (
                "Implement with Prometheus metrics and Sentry error tracking"
            )

        if "test" in name_lower or "validate" in name_lower:
            blueprint["libraries"].extend(["pytest", "hypothesis"])
            blueprint["requirements"].append("Automated testing framework")
            blueprint["blueprint"] = "Extend pytest suite with property-based testing"

        if "plan" in name_lower or "strateg" in name_lower:
            blueprint["requirements"].append("Advanced LLM integration")
            blueprint["env_vars"].extend(["OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
            blueprint["blueprint"] = "Use LLM chain-of-thought for multi-step planning"

        if "orchestrat" in name_lower or "parallel" in name_lower or "distribut" in name_lower:
            blueprint["libraries"].extend(["celery", "redis"])
            blueprint["requirements"].append("Distributed task queue")
            blueprint["blueprint"] = "Implement with Celery for distributed task execution"

        return blueprint

    def resource_request(self, capability_id: int) -> Optional[Dict[str, Any]]:
        """Check if a capability is viable but missing external resources.

        Args:
            capability_id: The ID of the capability to check

        Returns:
            Alert dictionary if resources are missing, None otherwise.
        """
        blueprint = self.check_requirements(capability_id)

        if "error" in blueprint:
            return None

        missing_resources: List[Dict[str, str]] = []

        for env_var in blueprint.get("env_vars", []):
            if not os.getenv(env_var):
                missing_resources.append({
                    "type": "environment_variable",
                    "name": env_var,
                    "description": f"Environment variable {env_var} is not set",
                })

        for lib in blueprint.get("libraries", []):
            try:
                __import__(lib.replace("-", "_"))
            except ImportError:
                missing_resources.append({
                    "type": "library",
                    "name": lib,
                    "description": f"Python library {lib} is not installed",
                })

        if missing_resources:
            return {
                "capability_id": capability_id,
                "capability_name": blueprint["capability_name"],
                "missing_resources": missing_resources,
                "alert_level": "warning",
                "message": (
                    f"Capability '{blueprint['capability_name']}' is viable but missing "
                    f"{len(missing_resources)} resource(s). Please provide the required "
                    "resources to activate this capability."
                ),
            }

        return None
