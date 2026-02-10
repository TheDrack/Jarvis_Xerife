# -*- coding: utf-8 -*-
"""
Capability Manager - JARVIS Self-Awareness Module

This service implements the intelligence layer for JARVIS self-awareness,
managing the 102 capabilities defined in JARVIS_OBJECTIVES_MAP.

The CapabilityManager can:
- Check requirements for capabilities
- Scan the repository to detect existing capabilities
- Request missing resources
- Determine the next evolution step

This is the foundation for JARVIS to understand what it can do,
what it cannot do, and what it needs to evolve.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

from sqlmodel import Session, create_engine, select
from sqlalchemy.engine import Engine

from app.domain.models.capability import JarvisCapability

logger = logging.getLogger(__name__)


class CapabilityManager:
    """
    Manages JARVIS self-awareness capabilities and evolution logic.
    
    This class implements the "How" layer - the intelligence that allows
    JARVIS to understand its own capabilities and guide its evolution.
    """
    
    def __init__(self, engine: Engine):
        """
        Initialize the Capability Manager
        
        Args:
            engine: SQLAlchemy engine for database operations
        """
        self.engine = engine
        self._capability_detectors = self._initialize_detectors()
    
    def _initialize_detectors(self) -> Dict[int, callable]:
        """
        Initialize capability detection functions.
        
        Returns a mapping of capability IDs to detection functions.
        Each function checks if that capability is implemented in the codebase.
        """
        # For now, we'll define a few example detectors
        # In a full implementation, each capability would have its own detector
        return {
            # Example detectors that check for existing functionality
            1: self._detect_capability_inventory,
            2: self._detect_capability_classification,
            16: self._detect_existing_capabilities_recognition,
        }
    
    def check_requirements(self, capability_id: int) -> Dict[str, Any]:
        """
        Generate a technical blueprint for a capability.
        
        For a 'nonexistent' capability, this method uses AI/logic to determine:
        - What libraries are needed
        - What APIs are required
        - What environment variables/keys are needed
        - What permissions are required
        
        Args:
            capability_id: The ID of the capability to check
            
        Returns:
            Dictionary containing:
            - requirements: List of technical requirements
            - libraries: List of Python libraries needed
            - apis: List of external APIs needed
            - env_vars: List of environment variables needed
            - permissions: List of permissions needed
            - blueprint: Technical description of implementation
        """
        with Session(self.engine) as session:
            capability = session.get(JarvisCapability, capability_id)
            if not capability:
                return {"error": f"Capability {capability_id} not found"}
            
            # Generate blueprint based on capability name and chapter
            blueprint = self._generate_blueprint(capability)
            
            return blueprint
    
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
    
    def status_scan(self) -> Dict[str, Any]:
        """
        Scan the repository to identify which capabilities are already implemented.
        
        This method:
        1. Checks the codebase for existing functionality
        2. Updates capability status (nonexistent -> partial or complete)
        3. Returns a summary of detected capabilities
        
        Returns:
            Dictionary with scan results:
            - total_capabilities: Total number of capabilities
            - nonexistent: Count of nonexistent capabilities
            - partial: Count of partial capabilities
            - complete: Count of complete capabilities
            - updated: List of capabilities that were updated
        """
        logger.info("Starting capability status scan...")
        
        updated_capabilities = []
        
        with Session(self.engine) as session:
            # Get all capabilities
            capabilities = session.exec(select(JarvisCapability)).all()
            
            for capability in capabilities:
                # Check if we have a detector for this capability
                detector = self._capability_detectors.get(capability.id)
                
                if detector:
                    new_status = detector()
                    if new_status and new_status != capability.status:
                        logger.info(f"Updating capability {capability.id}: {capability.status} -> {new_status}")
                        capability.status = new_status
                        updated_capabilities.append({
                            "id": capability.id,
                            "name": capability.capability_name,
                            "old_status": capability.status,
                            "new_status": new_status
                        })
            
            # Commit changes
            session.commit()
            
            # Generate summary
            all_capabilities = session.exec(select(JarvisCapability)).all()
            status_counts = {
                "nonexistent": sum(1 for c in all_capabilities if c.status == "nonexistent"),
                "partial": sum(1 for c in all_capabilities if c.status == "partial"),
                "complete": sum(1 for c in all_capabilities if c.status == "complete"),
            }
            
            logger.info(f"Scan complete. Updated {len(updated_capabilities)} capabilities.")
            
            return {
                "total_capabilities": len(all_capabilities),
                "nonexistent": status_counts["nonexistent"],
                "partial": status_counts["partial"],
                "complete": status_counts["complete"],
                "updated": updated_capabilities
            }
    
    def resource_request(self, capability_id: int) -> Optional[Dict[str, Any]]:
        """
        Check if a capability is viable but missing external resources.
        
        If a capability has all technical requirements satisfied but is missing
        external resources (API keys, permissions, etc.), generate an alert.
        
        Args:
            capability_id: The ID of the capability to check
            
        Returns:
            Alert dictionary if resources are missing, None otherwise:
            - capability_id: ID of the capability
            - capability_name: Name of the capability
            - missing_resources: List of missing resources
            - alert_level: 'warning' or 'error'
            - message: Human-readable alert message
        """
        blueprint = self.check_requirements(capability_id)
        
        if "error" in blueprint:
            return None
        
        missing_resources = []
        
        # Check for missing environment variables
        for env_var in blueprint.get("env_vars", []):
            if not os.getenv(env_var):
                missing_resources.append({
                    "type": "environment_variable",
                    "name": env_var,
                    "description": f"Environment variable {env_var} is not set"
                })
        
        # Check for missing libraries (this is a simplified check)
        for lib in blueprint.get("libraries", []):
            try:
                __import__(lib.replace("-", "_"))
            except ImportError:
                missing_resources.append({
                    "type": "library",
                    "name": lib,
                    "description": f"Python library {lib} is not installed"
                })
        
        if missing_resources:
            return {
                "capability_id": capability_id,
                "capability_name": blueprint["capability_name"],
                "missing_resources": missing_resources,
                "alert_level": "warning",
                "message": f"Capability '{blueprint['capability_name']}' is viable but missing {len(missing_resources)} resource(s). Please provide the required resources to activate this capability."
            }
        
        return None
    
    def get_next_evolution_step(self) -> Optional[Dict[str, Any]]:
        """
        Determine the next capability that JARVIS should implement.
        
        This is the self-evolution trigger. It returns the highest-priority
        capability that:
        1. Has status 'nonexistent' or 'partial'
        2. Has all technical requirements satisfied
        3. Is not blocked by missing external resources
        
        Priority is determined by:
        - Chapter (earlier chapters are more foundational)
        - Capability ID (lower IDs within a chapter are prioritized)
        
        Returns:
            Dictionary with next evolution step:
            - capability_id: ID of the capability to implement
            - capability_name: Name of the capability
            - chapter: Chapter this capability belongs to
            - current_status: Current implementation status
            - blueprint: Technical blueprint for implementation
            - priority_score: Priority score (lower is higher priority)
            
            Returns None if no capabilities are ready for implementation
        """
        logger.info("Determining next evolution step...")
        
        with Session(self.engine) as session:
            # Get all capabilities that are not complete, ordered by priority
            statement = (
                select(JarvisCapability)
                .where(JarvisCapability.status != "complete")
                .order_by(JarvisCapability.id)  # Lower IDs = higher priority
            )
            
            capabilities = session.exec(statement).all()
            
            for capability in capabilities:
                # Check if all requirements are satisfied
                alert = self.resource_request(capability.id)
                
                if alert is None:  # No missing resources
                    blueprint = self.check_requirements(capability.id)
                    
                    # Calculate priority score (lower = higher priority)
                    # Earlier chapters and lower IDs have higher priority
                    chapter_num = int(capability.chapter.split("_")[1])
                    priority_score = (chapter_num * 1000) + capability.id
                    
                    logger.info(f"Next evolution step: Capability {capability.id} - {capability.capability_name}")
                    
                    return {
                        "capability_id": capability.id,
                        "capability_name": capability.capability_name,
                        "chapter": capability.chapter,
                        "current_status": capability.status,
                        "blueprint": blueprint,
                        "priority_score": priority_score
                    }
            
            logger.info("No capabilities ready for implementation (all have missing resources or are complete)")
            return None
    
    def get_evolution_progress(self) -> Dict[str, Any]:
        """
        Get overall evolution progress and chapter-by-chapter breakdown.
        
        Returns:
            Dictionary with evolution progress:
            - overall_progress: Overall percentage (0-100)
            - total_capabilities: Total number of capabilities
            - complete_capabilities: Number of complete capabilities
            - partial_capabilities: Number of partial capabilities
            - nonexistent_capabilities: Number of nonexistent capabilities
            - chapters: List of chapter progress data
        """
        with Session(self.engine) as session:
            capabilities = session.exec(select(JarvisCapability)).all()
            
            # Overall counts
            total = len(capabilities)
            complete = sum(1 for c in capabilities if c.status == "complete")
            partial = sum(1 for c in capabilities if c.status == "partial")
            nonexistent = sum(1 for c in capabilities if c.status == "nonexistent")
            
            # Calculate overall progress (complete = 100%, partial = 50%, nonexistent = 0%)
            overall_progress = ((complete * 100 + partial * 50) / total) if total > 0 else 0
            
            # Group by chapter
            chapters = {}
            for capability in capabilities:
                if capability.chapter not in chapters:
                    chapters[capability.chapter] = {
                        "chapter": capability.chapter,
                        "total": 0,
                        "complete": 0,
                        "partial": 0,
                        "nonexistent": 0
                    }
                
                chapters[capability.chapter]["total"] += 1
                if capability.status == "complete":
                    chapters[capability.chapter]["complete"] += 1
                elif capability.status == "partial":
                    chapters[capability.chapter]["partial"] += 1
                else:
                    chapters[capability.chapter]["nonexistent"] += 1
            
            # Calculate progress for each chapter
            chapter_list = []
            for chapter_name, stats in sorted(chapters.items()):
                chapter_progress = (
                    (stats["complete"] * 100 + stats["partial"] * 50) / stats["total"]
                    if stats["total"] > 0 else 0
                )
                chapter_list.append({
                    **stats,
                    "progress_percentage": round(chapter_progress, 2)
                })
            
            return {
                "overall_progress": round(overall_progress, 2),
                "total_capabilities": total,
                "complete_capabilities": complete,
                "partial_capabilities": partial,
                "nonexistent_capabilities": nonexistent,
                "chapters": chapter_list
            }
    
    # Detector methods for specific capabilities
    
    def _detect_capability_inventory(self) -> str:
        """Detect if capability #1 (internal inventory) is implemented"""
        # Check if we have the capabilities.json and database table
        json_path = Path(__file__).parent.parent.parent.parent / "data" / "capabilities.json"
        if json_path.exists():
            with Session(self.engine) as session:
                count = len(session.exec(select(JarvisCapability)).all())
                if count >= 102:
                    return "complete"
                elif count > 0:
                    return "partial"
        return "nonexistent"
    
    def _detect_capability_classification(self) -> str:
        """Detect if capability #2 (classification by status) is implemented"""
        # Check if status field is being used
        with Session(self.engine) as session:
            capabilities = session.exec(select(JarvisCapability)).all()
            if len(capabilities) > 0:
                # Check if any capabilities have non-default status
                non_default = sum(1 for c in capabilities if c.status != "nonexistent")
                if non_default > 0:
                    return "complete"
                else:
                    return "partial"
        return "nonexistent"
    
    def _detect_existing_capabilities_recognition(self) -> str:
        """Detect if capability #16 (recognize existing capabilities) is implemented"""
        # Check if the CapabilityManager class exists and has detectors
        if len(self._capability_detectors) > 0:
            return "partial"
        return "nonexistent"
