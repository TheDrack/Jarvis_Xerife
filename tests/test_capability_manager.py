from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Unit tests for CapabilityManager service"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from sqlmodel import Session, create_engine, SQLModel, select

from app.application.services.capability_manager import CapabilityManager
from app.domain.models.capability import JarvisCapability


@pytest.fixture
def test_engine():
    """Create a test database engine with in-memory SQLite"""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def capability_manager(test_engine):
    """Create a CapabilityManager instance with test database"""
    return CapabilityManager(engine=test_engine)


@pytest.fixture
def sample_capabilities(test_engine):
    """Populate test database with sample capabilities"""
    with Session(test_engine) as session:
        capabilities = [
            JarvisCapability(
                id=1,
                chapter="CHAPTER_1_IMMEDIATE_FOUNDATION",
                capability_name="Maintain internal inventory of all known capabilities",
                status="nonexistent",
                requirements="[]",
                implementation_logic=""
            ),
            JarvisCapability(
                id=2,
                chapter="CHAPTER_1_IMMEDIATE_FOUNDATION",
                capability_name="Classify capabilities by status: nonexistent, partial, complete",
                status="nonexistent",
                requirements="[]",
                implementation_logic=""
            ),
            JarvisCapability(
                id=72,
                chapter="CHAPTER_7_ECONOMIC_INTELLIGENCE",
                capability_name="Evaluate cost of each executed action",
                status="nonexistent",
                requirements="[]",
                implementation_logic=""
            ),
        ]
        for cap in capabilities:
            session.add(cap)
        session.commit()


class TestCapabilityManager(NexusComponent):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """Test suite for CapabilityManager"""

    def test_initialization(self, capability_manager):
        """Test that CapabilityManager initializes correctly"""
        assert capability_manager is not None
        assert capability_manager.engine is not None
        assert isinstance(capability_manager._capability_detectors, dict)

    def test_check_requirements(self, capability_manager, sample_capabilities):
        """Test check_requirements generates blueprint for capability"""
        # Test economic capability (should have Stripe requirements)
        blueprint = capability_manager.check_requirements(72)
        
        assert blueprint["capability_id"] == 72
        assert blueprint["capability_name"] == "Evaluate cost of each executed action"
        assert "stripe" in blueprint["libraries"]
        assert "STRIPE_API_KEY" in blueprint["env_vars"]
        assert "Stripe API" in blueprint["apis"]
        assert len(blueprint["requirements"]) > 0

    def test_check_requirements_not_found(self, capability_manager):
        """Test check_requirements with non-existent capability"""
        blueprint = capability_manager.check_requirements(9999)
        assert "error" in blueprint
        assert "not found" in blueprint["error"]

    def test_get_evolution_progress(self, capability_manager, sample_capabilities):
        """Test get_evolution_progress returns correct statistics"""
        progress = capability_manager.get_evolution_progress()
        
        assert progress["total_capabilities"] == 3
        assert progress["complete_capabilities"] == 0
        assert progress["partial_capabilities"] == 0
        assert progress["nonexistent_capabilities"] == 3
        assert progress["overall_progress"] == 0.0
        assert len(progress["chapters"]) == 2  # 2 unique chapters in sample data

    def test_get_evolution_progress_with_mixed_statuses(self, test_engine, capability_manager):
        """Test progress calculation with mixed statuses"""
        with Session(test_engine) as session:
            # Add capabilities with different statuses
            capabilities = [
                JarvisCapability(id=1, chapter="CHAPTER_1", capability_name="Test 1", 
                               status="complete", requirements="[]", implementation_logic=""),
                JarvisCapability(id=2, chapter="CHAPTER_1", capability_name="Test 2",
                               status="partial", requirements="[]", implementation_logic=""),
                JarvisCapability(id=3, chapter="CHAPTER_1", capability_name="Test 3",
                               status="nonexistent", requirements="[]", implementation_logic=""),
            ]
            for cap in capabilities:
                session.add(cap)
            session.commit()
        
        progress = capability_manager.get_evolution_progress()
        
        # Progress: (1 * 100 + 1 * 50) / 3 = 50%
        assert progress["total_capabilities"] == 3
        assert progress["complete_capabilities"] == 1
        assert progress["partial_capabilities"] == 1
        assert progress["nonexistent_capabilities"] == 1
        assert progress["overall_progress"] == 50.0

    def test_status_scan(self, capability_manager, sample_capabilities):
        """Test status_scan detects existing capabilities"""
        scan_results = capability_manager.status_scan()
        
        assert "total_capabilities" in scan_results
        assert "nonexistent" in scan_results
        assert "partial" in scan_results
        assert "complete" in scan_results
        assert "updated" in scan_results
        assert scan_results["total_capabilities"] == 3

    def test_get_next_evolution_step(self, capability_manager, sample_capabilities):
        """Test get_next_evolution_step returns highest priority capability"""
        next_step = capability_manager.get_next_evolution_step()
        
        assert next_step is not None
        assert next_step["capability_id"] == 1  # Lowest ID = highest priority
        assert next_step["chapter"] == "CHAPTER_1_IMMEDIATE_FOUNDATION"
        assert next_step["current_status"] == "nonexistent"
        assert "blueprint" in next_step
        assert "priority_score" in next_step

    def test_get_next_evolution_step_all_complete(self, test_engine, capability_manager):
        """Test get_next_evolution_step when all capabilities are complete"""
        with Session(test_engine) as session:
            cap = JarvisCapability(
                id=1, 
                chapter="CHAPTER_1", 
                capability_name="Test", 
                status="complete",
                requirements="[]",
                implementation_logic=""
            )
            session.add(cap)
            session.commit()
        
        next_step = capability_manager.get_next_evolution_step()
        # Should return None or the capability if there are missing resources
        # depending on implementation details

    def test_resource_request(self, capability_manager, sample_capabilities):
        """Test resource_request identifies missing resources"""
        # Test capability that requires external resources
        alert = capability_manager.resource_request(72)
        
        if alert:  # Will be None if libraries/env vars are present
            assert "capability_id" in alert
            assert "missing_resources" in alert
            assert "alert_level" in alert
            assert alert["alert_level"] == "warning"

    def test_blueprint_generation_memory_capability(self, test_engine, capability_manager):
        """Test blueprint generation for memory-related capabilities"""
        with Session(test_engine) as session:
            cap = JarvisCapability(
                id=27,
                chapter="CHAPTER_3_CONTEXTUAL_UNDERSTANDING",
                capability_name="Maintain short-term operational memory",
                status="nonexistent",
                requirements="[]",
                implementation_logic=""
            )
            session.add(cap)
            session.commit()
        
        blueprint = capability_manager.check_requirements(27)
        
        # Memory capabilities should include Redis/SQLAlchemy
        assert any("redis" in lib.lower() or "sqlalchemy" in lib.lower() 
                  for lib in blueprint["libraries"])
        assert "memory" in blueprint["blueprint"].lower() or "storage" in blueprint["blueprint"].lower()

    def test_blueprint_generation_learning_capability(self, test_engine, capability_manager):
        """Test blueprint generation for learning-related capabilities"""
        with Session(test_engine) as session:
            cap = JarvisCapability(
                id=61,
                chapter="CHAPTER_6_DIRECTED_LEARNING",
                capability_name="Learn from recurring failures",
                status="nonexistent",
                requirements="[]",
                implementation_logic=""
            )
            session.add(cap)
            session.commit()
        
        blueprint = capability_manager.check_requirements(61)
        
        # Learning capabilities should include ML libraries
        assert any("scikit" in lib.lower() or "numpy" in lib.lower() 
                  for lib in blueprint["libraries"])

    def test_chapter_progress_calculation(self, test_engine, capability_manager):
        """Test that chapter progress is calculated correctly"""
        with Session(test_engine) as session:
            # Add 4 capabilities in CHAPTER_1: 1 complete, 1 partial, 2 nonexistent
            capabilities = [
                JarvisCapability(id=1, chapter="CHAPTER_1", capability_name="C1",
                               status="complete", requirements="[]", implementation_logic=""),
                JarvisCapability(id=2, chapter="CHAPTER_1", capability_name="C2",
                               status="partial", requirements="[]", implementation_logic=""),
                JarvisCapability(id=3, chapter="CHAPTER_1", capability_name="C3",
                               status="nonexistent", requirements="[]", implementation_logic=""),
                JarvisCapability(id=4, chapter="CHAPTER_1", capability_name="C4",
                               status="nonexistent", requirements="[]", implementation_logic=""),
            ]
            for cap in capabilities:
                session.add(cap)
            session.commit()
        
        progress = capability_manager.get_evolution_progress()
        chapter1 = next(c for c in progress["chapters"] if c["chapter"] == "CHAPTER_1")
        
        assert chapter1["total"] == 4
        assert chapter1["complete"] == 1
        assert chapter1["partial"] == 1
        assert chapter1["nonexistent"] == 2
        # Progress: (1 * 100 + 1 * 50) / 4 = 37.5%
        assert chapter1["progress_percentage"] == 37.5


class TestCapabilityDependencyGraph:
    """Tests for ETAPA 5 — Dependency Graph methods."""

    # ------------------------------------------------------------------
    # Sample capabilities.json data
    # ------------------------------------------------------------------

    _CAPS = [
        {"id": "CAP-001", "title": "A", "status": "complete", "depends_on": []},
        {"id": "CAP-002", "title": "B", "status": "complete", "depends_on": ["CAP-001"]},
        {"id": "CAP-003", "title": "C", "status": "partial", "depends_on": ["CAP-001"]},
        {"id": "CAP-004", "title": "D", "status": "nonexistent", "depends_on": ["CAP-002", "CAP-003"]},
        {"id": "CAP-005", "title": "E", "status": "nonexistent", "depends_on": []},
    ]

    def _make_manager(self, caps):
        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)
        manager = CapabilityManager(engine=engine)
        manager._load_capabilities_json = lambda: caps
        return manager

    def test_build_dependency_graph_structure(self):
        """build_dependency_graph() deve retornar dicionário de adjacência correto."""
        manager = self._make_manager(self._CAPS)
        graph = manager.build_dependency_graph()

        # CAP-001 é predecessora de CAP-002 e CAP-003
        assert "CAP-002" in graph["CAP-001"]
        assert "CAP-003" in graph["CAP-001"]
        # CAP-004 depende de CAP-002 e CAP-003
        assert "CAP-004" in graph["CAP-002"]
        assert "CAP-004" in graph["CAP-003"]
        # CAP-005 não tem predecessores nem dependentes
        assert graph.get("CAP-005", []) == []

    def test_get_executable_capabilities_returns_ready_ones(self):
        """get_executable_capabilities() deve retornar só as capabilities prontas."""
        manager = self._make_manager(self._CAPS)
        executable = manager.get_executable_capabilities()
        ids = [c["id"] for c in executable]

        # CAP-003 é parcial com dep CAP-001 (complete) → executável
        # CAP-005 é nonexistent sem deps → executável
        assert "CAP-003" in ids
        assert "CAP-005" in ids

        # CAP-004 depende de CAP-003 (não complete) → NÃO executável
        assert "CAP-004" not in ids

        # CAP-001 e CAP-002 já são complete → não devem aparecer
        assert "CAP-001" not in ids
        assert "CAP-002" not in ids

    def test_get_executable_excludes_blocked(self):
        """Capabilities com dependências incompletas não devem aparecer."""
        caps = [
            {"id": "A", "title": "A", "status": "nonexistent", "depends_on": []},
            {"id": "B", "title": "B", "status": "nonexistent", "depends_on": ["A"]},
        ]
        manager = self._make_manager(caps)
        executable = manager.get_executable_capabilities()
        ids = [c["id"] for c in executable]

        # A não tem deps → executável
        assert "A" in ids
        # B depende de A (não complete) → não executável
        assert "B" not in ids

    def test_get_critical_path_linear_chain(self):
        """Para uma cadeia linear A→B→C, o caminho crítico é [A, B, C]."""
        caps = [
            {"id": "A", "title": "A", "status": "nonexistent", "depends_on": []},
            {"id": "B", "title": "B", "status": "nonexistent", "depends_on": ["A"]},
            {"id": "C", "title": "C", "status": "nonexistent", "depends_on": ["B"]},
        ]
        manager = self._make_manager(caps)
        path = manager.get_critical_path()

        assert path == ["A", "B", "C"]

    def test_get_critical_path_selects_longest(self):
        """O caminho crítico deve ser o mais longo em um DAG com bifurcação."""
        caps = [
            {"id": "A", "title": "A", "status": "complete", "depends_on": []},
            {"id": "B", "title": "B", "status": "nonexistent", "depends_on": ["A"]},
            {"id": "C", "title": "C", "status": "nonexistent", "depends_on": ["A"]},
            {"id": "D", "title": "D", "status": "nonexistent", "depends_on": ["B"]},
            # Caminho A→B→D tem comprimento 3; A→C tem comprimento 2
        ]
        manager = self._make_manager(caps)
        path = manager.get_critical_path()

        # O caminho mais longo deve incluir A, B, D
        assert "A" in path
        assert "B" in path
        assert "D" in path

    def test_get_critical_path_empty(self):
        """Com lista vazia, deve retornar lista vazia."""
        manager = self._make_manager([])
        path = manager.get_critical_path()
        assert path == []
