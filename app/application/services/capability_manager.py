from app.core.nexus import NexusComponent
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
from typing import Dict, List, Optional, Any, Set

from sqlmodel import Session, create_engine, select
from sqlalchemy.engine import Engine

from app.domain.models.capability import JarvisCapability

logger = logging.getLogger(__name__)


class CapabilityManager(NexusComponent):
    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    """
    Manages JARVIS self-awareness capabilities and evolution logic.
    
    This class implements the "How" layer - the intelligence that allows
    JARVIS to understand its own capabilities and guide its evolution.
    
    IMPORTANT PROTOCOL CHANGE:
    - It is STRICTLY PROHIBITED to create GitHub Issues for test errors or capability gaps
    - Instead, use report_capability_gap_via_pr() which creates a Pull Request
    - Flow: Detect Gap -> Create Branch -> Open PR with autonomous_instruction.json
    - The PR triggers the Jarvis Autonomous State Machine for automatic implementation
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
        from app.application.services.capability_detectors import (
            detect_capability_inventory,
            detect_capability_classification,
            detect_existing_capabilities_recognition,
        )
        return {
            1: lambda: detect_capability_inventory(self.engine),
            2: lambda: detect_capability_classification(self.engine),
            16: lambda: detect_existing_capabilities_recognition(self._capability_detectors),
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
        """Backward compatible delegator - see capability_detectors.detect_capability_inventory"""
        from app.application.services.capability_detectors import detect_capability_inventory
        return detect_capability_inventory(self.engine)
    
    def _detect_capability_classification(self) -> str:
        """Backward compatible delegator - see capability_detectors.detect_capability_classification"""
        from app.application.services.capability_detectors import detect_capability_classification
        return detect_capability_classification(self.engine)
    
    def _detect_existing_capabilities_recognition(self) -> str:
        """Backward compatible delegator - see capability_detectors.detect_existing_capabilities_recognition"""
        from app.application.services.capability_detectors import detect_existing_capabilities_recognition
        return detect_existing_capabilities_recognition(self._capability_detectors)
    
    async def report_capability_gap_via_pr(
        self,
        capability_id: int,
        github_adapter=None
    ) -> Dict[str, Any]:
        """Backward compatible delegator - see CapabilityGapReporter.report_capability_gap_via_pr"""
        from app.application.services.capability_gap_reporter import CapabilityGapReporter
        reporter = CapabilityGapReporter(self.engine)
        return await reporter.report_capability_gap_via_pr(capability_id, github_adapter)

    # ------------------------------------------------------------------
    # Dependency Graph methods (ETAPA 5)
    # ------------------------------------------------------------------

    def build_dependency_graph(self) -> Dict[str, List[str]]:
        """Constrói um grafo de dependências das capabilities como dicionário de adjacência.

        Lê o campo ``depends_on`` de cada capability em data/capabilities.json
        e retorna um grafo orientado onde cada chave é o ID da capability e o
        valor é a lista de capability IDs que dependem dela (dependentes).

        Returns:
            Dicionário de adjacência: {capability_id: [ids_que_dependem_dele]}
        """
        caps = self._load_capabilities_json()
        graph: Dict[str, List[str]] = {cap["id"]: [] for cap in caps}
        for cap in caps:
            for dep in cap.get("depends_on", []):
                if dep in graph:
                    graph[dep].append(cap["id"])
                else:
                    graph[dep] = [cap["id"]]
        return graph

    def get_executable_capabilities(self) -> List[Dict[str, Any]]:
        """Retorna capabilities cujas dependências estão com status ``complete``.

        Apenas essas capabilities podem ser trabalhadas no próximo ciclo
        de evolução.

        Returns:
            Lista de dicionários de capabilities prontas para execução.
        """
        caps = self._load_capabilities_json()
        caps_by_id: Dict[str, Dict[str, Any]] = {c["id"]: c for c in caps}

        executable = []
        for cap in caps:
            if cap.get("status") == "complete":
                continue  # já concluída
            deps = cap.get("depends_on", [])
            if all(caps_by_id.get(dep, {}).get("status") == "complete" for dep in deps):
                executable.append(cap)
        return executable

    def get_critical_path(self) -> List[str]:
        """Retorna o caminho crítico do DAG de capabilities (sequência mais longa).

        O caminho crítico representa o gargalo do plano de evolução.
        Utiliza ordenação topológica para calcular a distância máxima.

        Returns:
            Lista de capability IDs no caminho crítico (do início ao fim).
        """
        caps = self._load_capabilities_json()
        caps_by_id: Dict[str, Dict[str, Any]] = {c["id"]: c for c in caps}

        # Constrói grafo de dependências (dep → cap que depende dela)
        # Para critical path precisamos: predecessors[cap] = depends_on
        predecessors: Dict[str, List[str]] = {
            c["id"]: list(c.get("depends_on", [])) for c in caps
        }
        all_ids = list(caps_by_id.keys())

        # Ordenação topológica (Kahn's algorithm)
        in_degree: Dict[str, int] = {cid: len(predecessors.get(cid, [])) for cid in all_ids}
        queue: List[str] = [cid for cid in all_ids if in_degree[cid] == 0]
        topo_order: List[str] = []

        # successors: para cada cap, quem vem depois (quem a lista como dependência)
        successors: Dict[str, List[str]] = {cid: [] for cid in all_ids}
        for cid in all_ids:
            for dep in predecessors.get(cid, []):
                if dep in successors:
                    successors[dep].append(cid)

        visited: List[str] = []
        while queue:
            queue.sort()  # garante ordenação determinística para produzir caminho crítico estável
            node = queue.pop(0)
            topo_order.append(node)
            for succ in successors.get(node, []):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        # Distância mais longa (longest path)
        dist: Dict[str, int] = {cid: 0 for cid in all_ids}
        prev: Dict[str, Optional[str]] = {cid: None for cid in all_ids}

        for node in topo_order:
            for succ in successors.get(node, []):
                if dist[node] + 1 > dist[succ]:
                    dist[succ] = dist[node] + 1
                    prev[succ] = node

        # Encontra o nó com maior distância
        if not dist:
            return []
        end_node = max(dist, key=lambda cid: dist[cid])

        # Reconstrói o caminho
        path: List[str] = []
        current: Optional[str] = end_node
        while current is not None:
            path.append(current)
            current = prev[current]
        path.reverse()
        return path

    def _load_capabilities_json(self) -> List[Dict[str, Any]]:
        """Lê data/capabilities.json e retorna a lista de capabilities."""
        _file = Path("data/capabilities.json")
        if not _file.exists():
            return []
        try:
            data = json.loads(_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return data.get("capabilities", [])
        except Exception as exc:
            logger.warning("[CapabilityManager] Falha ao ler capabilities.json: %s", exc)
            return []
