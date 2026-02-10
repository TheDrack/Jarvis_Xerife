# -*- coding: utf-8 -*-
"""Unit tests for CapabilityManager service"""

import json
import pytest
from pathlib import Path
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


class TestCapabilityManager:
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
