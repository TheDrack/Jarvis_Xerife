# -*- coding: utf-8 -*-
"""Tests for Xerife Strategist Service"""

from pathlib import Path

import pytest

from app.application.services.strategist_service import (
    BudgetExceededException,
    StrategistService,
)
from app.domain.models.viability import (
    CostEstimate,
    ImpactEstimate,
    ImpactLevel,
    RiskEstimate,
    RiskLevel,
    ViabilityMatrix,
)
from app.utils.document_store import document_store


@pytest.fixture
def temp_proposals_dir(tmp_path):
    """Create temporary proposals directory"""
    proposals_dir = tmp_path / "proposals"
    return proposals_dir


@pytest.fixture
def strategist(temp_proposals_dir):
    """Create StrategistService instance with temp directory"""
    return StrategistService(
        proposals_dir=temp_proposals_dir,
        default_budget_cap=10.0,
        min_roi_threshold=0.5,
    )


def test_viability_matrix_roi_calculation():
    """Test ROI calculation in ViabilityMatrix"""
    cost = CostEstimate(
        api_cost_usd=1.0,
        code_complexity="simple",
        development_time_hours=1.0,
    )
    impact = ImpactEstimate(
        performance_gain_percent=20.0,
        user_utility_level=ImpactLevel.MEDIUM,
    )
    risk = RiskEstimate(risk_level=RiskLevel.LOW)
    
    matrix = ViabilityMatrix(
        cost=cost,
        impact=impact,
        risk=risk,
        proposal_title="Test Proposal",
        proposal_description="Test description",
    )
    
    roi = matrix.calculate_roi()
    assert roi > 0  # Should have positive ROI
    
    # Test scoring
    assert 0 <= cost.total_cost_score() <= 10
    assert 0 <= impact.total_impact_score() <= 10
    assert 0 <= risk.total_risk_score() <= 10


def test_viability_matrix_approval_logic():
    """Test approval logic based on ROI and risk"""
    # Good proposal - should be approved
    good_matrix = ViabilityMatrix(
        cost=CostEstimate(api_cost_usd=0.5, code_complexity="simple"),
        impact=ImpactEstimate(
            performance_gain_percent=30.0,
            user_utility_level=ImpactLevel.HIGH,
        ),
        risk=RiskEstimate(risk_level=RiskLevel.LOW),
        proposal_title="Good Proposal",
        proposal_description="Good",
    )
    assert good_matrix.is_viable()
    
    # Critical risk - should be rejected
    critical_risk_matrix = ViabilityMatrix(
        cost=CostEstimate(api_cost_usd=0.5),
        impact=ImpactEstimate(user_utility_level=ImpactLevel.HIGH),
        risk=RiskEstimate(risk_level=RiskLevel.CRITICAL),
        proposal_title="Critical Risk",
        proposal_description="Critical",
    )
    assert not critical_risk_matrix.is_viable()
    
    # Security concerns without mitigation - should be rejected
    security_matrix = ViabilityMatrix(
        cost=CostEstimate(api_cost_usd=0.5),
        impact=ImpactEstimate(user_utility_level=ImpactLevel.MEDIUM),
        risk=RiskEstimate(
            risk_level=RiskLevel.MEDIUM,
            security_concerns=True,
            mitigation_strategy="",
        ),
        proposal_title="Security Issue",
        proposal_description="Security",
    )
    assert not security_matrix.is_viable()


def test_strategist_generate_viability_matrix(strategist):
    """Test viability matrix generation"""
    cost = CostEstimate(api_cost_usd=2.0, code_complexity="moderate")
    impact = ImpactEstimate(
        performance_gain_percent=25.0,
        user_utility_level=ImpactLevel.MEDIUM,
    )
    risk = RiskEstimate(risk_level=RiskLevel.LOW)
    
    matrix = strategist.generate_viability_matrix(
        proposal_title="Test Feature",
        proposal_description="Add new feature",
        cost=cost,
        impact=impact,
        risk=risk,
    )
    
    assert matrix.proposal_title == "Test Feature"
    assert matrix.proposal_id.startswith("test-feature-")
    assert matrix.calculate_roi() > 0
    assert matrix.approved is False


def test_strategist_archive_proposal(strategist):
    """Test proposal archiving"""
    cost = CostEstimate(api_cost_usd=1.0)
    impact = ImpactEstimate(user_utility_level=ImpactLevel.HIGH)
    risk = RiskEstimate(risk_level=RiskLevel.LOW)
    
    # Create approved matrix
    matrix = strategist.generate_viability_matrix(
        proposal_title="Archive Test",
        proposal_description="Test archiving",
        cost=cost,
        impact=impact,
        risk=risk,
    )
    
    # Archive it
    filepath = strategist.archive_proposal(matrix)
    
    # Verify file exists
    assert filepath.exists()
    
    # A viable proposal remains pending until an explicit human approval.
    assert filepath.parent.name == "pending"
    
    # Verify content
    data = document_store.read(filepath)
    
    assert data['proposal_title'] == "Archive Test"
    assert data['viable'] is True
    assert data['approved'] is False
    assert data['status'] == 'pending'




def test_strategist_approve_proposal_records_human_decision(strategist):
    cost = CostEstimate(api_cost_usd=1.0)
    impact = ImpactEstimate(user_utility_level=ImpactLevel.HIGH)
    risk = RiskEstimate(risk_level=RiskLevel.LOW)
    matrix = strategist.generate_viability_matrix(
        proposal_title="Approval Gate",
        proposal_description="Must wait for explicit human approval.",
        cost=cost,
        impact=impact,
        risk=risk,
    )
    pending_path = strategist.archive_proposal(matrix)

    approved_path = strategist.approve_proposal(
        pending_path.name,
        approved_by="commander",
    )

    assert approved_path.parent == strategist.approved_dir
    assert not pending_path.exists()
    data = document_store.read(approved_path)
    assert data["viable"] is True
    assert data["approved"] is True
    assert data["status"] == "approved"
    assert data["approved_by"] == "commander"
    assert data["approved_at"]


def test_strategist_approval_rejects_path_traversal(strategist):
    with pytest.raises(ValueError, match="Invalid proposal filename"):
        strategist.approve_proposal("../approved/other.jrvs")



def test_strategist_approval_requires_a_nonempty_human_identity(strategist):
    matrix = strategist.generate_viability_matrix(
        proposal_title="Actor Required",
        proposal_description="Approval must be attributable.",
        cost=CostEstimate(api_cost_usd=1.0),
        impact=ImpactEstimate(user_utility_level=ImpactLevel.HIGH),
        risk=RiskEstimate(risk_level=RiskLevel.LOW),
    )
    pending_path = strategist.archive_proposal(matrix)

    with pytest.raises(ValueError, match="approved_by"):
        strategist.approve_proposal(pending_path.name)

    with pytest.raises(ValueError, match="approved_by"):
        strategist.approve_proposal(pending_path.name, approved_by="  ")

    assert pending_path.exists()
    assert not list(strategist.approved_dir.glob("*.jrvs"))


def test_generate_rfc_requires_a_persisted_human_approval(strategist):
    matrix = strategist.generate_viability_matrix(
        proposal_title="Persisted Approval",
        proposal_description="An in-memory boolean is not an approval record.",
        cost=CostEstimate(api_cost_usd=1.0),
        impact=ImpactEstimate(user_utility_level=ImpactLevel.HIGH),
        risk=RiskEstimate(risk_level=RiskLevel.LOW),
    )
    matrix.approved = True

    with pytest.raises(ValueError, match="persisted human approval"):
        strategist.generate_rfc(matrix)

    pending_path = strategist.archive_proposal(matrix)
    strategist.approve_proposal(pending_path.name, approved_by="commander")

    # The persisted approval record is authoritative; a mutable in-memory
    # boolean does not have to be set by the caller.
    matrix.approved = False
    rfc_path = strategist.generate_rfc(matrix)
    assert rfc_path.exists()


def test_strategist_execute_archives_viable_proposal_as_pending(strategist):
    result = strategist.execute(
        {
            "action": "evaluate_proposal",
            "proposal_title": "Execute Gate",
            "proposal_description": "Create a proposal without auto-approval.",
            "cost": {"api_cost_usd": 1.0, "code_complexity": "simple"},
            "impact": {"user_utility_level": "high", "performance_gain_percent": 25.0},
            "risk": {"risk_level": "low"},
        }
    )

    assert result["success"] is True
    assert result["status"] == "pending"
    assert result["viable"] is True
    assert result["approved"] is False
    assert result["approval_required"] is True
    assert Path(result["proposal_path"]).parent.name == "pending"
    assert "APROVAR (aguardando decisão humana)" in result["decision_prompt"]
    assert "Posso prosseguir" in result["decision_prompt"]


def test_strategist_archive_rejected_proposal(strategist):
    """Test archiving rejected proposal"""
    # Create proposal with critical risk
    cost = CostEstimate(api_cost_usd=1.0)
    impact = ImpactEstimate(user_utility_level=ImpactLevel.LOW)
    risk = RiskEstimate(risk_level=RiskLevel.CRITICAL)
    
    matrix = strategist.generate_viability_matrix(
        proposal_title="Rejected Test",
        proposal_description="Should be rejected",
        cost=cost,
        impact=impact,
        risk=risk,
    )
    
    # Archive it
    filepath = strategist.archive_proposal(matrix)
    
    # Verify it's in rejected directory
    assert "rejected" in str(filepath)
    
    # Verify rejection reason
    data = document_store.read(filepath)
    
    assert data['viable'] is False
    assert data['rejection_reason'] != ""


def test_strategist_generate_rfc(strategist):
    """Test RFC generation for approved proposals"""
    cost = CostEstimate(api_cost_usd=1.0)
    impact = ImpactEstimate(user_utility_level=ImpactLevel.HIGH)
    risk = RiskEstimate(risk_level=RiskLevel.LOW)
    
    matrix = strategist.generate_viability_matrix(
        proposal_title="RFC Test",
        proposal_description="Test RFC generation",
        cost=cost,
        impact=impact,
        risk=risk,
    )
    
    pending_path = strategist.archive_proposal(matrix)
    strategist.approve_proposal(pending_path.name, approved_by="commander")
    rfc_path = strategist.generate_rfc(matrix)
    
    # Verify file exists
    assert rfc_path.exists()
    assert rfc_path.name.startswith("RFC-")
    assert rfc_path.suffix == ".md"
    
    # Verify content
    content = rfc_path.read_text()
    assert "RFC Test" in content
    assert "Test RFC generation" in content
    assert "ROI Score" in content




def test_strategist_rfc_requires_explicit_human_approval(strategist):
    matrix = strategist.generate_viability_matrix(
        proposal_title="RFC Approval Gate",
        proposal_description="Viable work still requires human approval.",
        cost=CostEstimate(api_cost_usd=1.0),
        impact=ImpactEstimate(user_utility_level=ImpactLevel.HIGH),
        risk=RiskEstimate(risk_level=RiskLevel.LOW),
    )

    assert matrix.is_viable()
    assert matrix.approved is False
    with pytest.raises(ValueError, match="explicit human approval"):
        strategist.generate_rfc(matrix)


def test_strategist_rfc_rejected_proposal_fails(strategist):
    """Test that RFC generation fails for rejected proposals"""
    cost = CostEstimate(api_cost_usd=1.0)
    impact = ImpactEstimate(user_utility_level=ImpactLevel.LOW)
    risk = RiskEstimate(risk_level=RiskLevel.CRITICAL)
    
    matrix = strategist.generate_viability_matrix(
        proposal_title="Rejected",
        proposal_description="Test",
        cost=cost,
        impact=impact,
        risk=risk,
    )
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Cannot generate RFC"):
        strategist.generate_rfc(matrix)


def test_strategist_format_decision_prompt(strategist):
    """Test decision prompt formatting"""
    cost = CostEstimate(api_cost_usd=2.5, development_time_hours=3.0)
    impact = ImpactEstimate(
        performance_gain_percent=40.0,
        user_utility_level=ImpactLevel.HIGH,
    )
    risk = RiskEstimate(
        risk_level=RiskLevel.MEDIUM,
        risk_description="May affect legacy code",
        mitigation_strategy="Add comprehensive tests",
    )
    
    matrix = strategist.generate_viability_matrix(
        proposal_title="Decision Test",
        proposal_description="Test decision interface",
        cost=cost,
        impact=impact,
        risk=risk,
    )
    
    prompt = strategist.format_decision_prompt(matrix)
    
    # Verify prompt content
    assert "Comandante" in prompt
    assert "oportunidade de melhoria" in prompt
    assert "Decision Test" in prompt
    assert "$2.50" in prompt
    assert "3.0h" in prompt
    assert "May affect legacy code" in prompt
    assert "Add comprehensive tests" in prompt
    assert "Posso prosseguir" in prompt


def test_strategist_budget_check(strategist):
    """Test budget checking"""
    # Within budget
    cost, within = strategist.check_budget(
        used_tokens=1000,
        token_cost_per_1k=0.001,
    )
    assert cost == 0.001
    assert within is True
    
    # Exceed budget
    with pytest.raises(BudgetExceededException) as exc_info:
        strategist.check_budget(
            used_tokens=20_000_000,  # 20M tokens
            token_cost_per_1k=0.001,
        )
    
    assert exc_info.value.used > strategist.default_budget_cap


def test_strategist_error_log_analysis(strategist):
    """Test error log analysis for refactoring suggestions"""
    error_logs = [
        {"error_message": "NoneType object has no attribute 'value'", "error_type": "AttributeError", "count": 5},
        {"error_message": "Division by zero", "error_type": "ZeroDivisionError", "count": 3},
        {"error_message": "Connection timeout", "error_type": "TimeoutError", "count": 1},
    ]
    
    suggestions = strategist.analyze_error_logs(error_logs)
    
    # Should have 2 suggestions (only errors with count >= 3)
    assert len(suggestions) == 2
    
    # Verify suggestions mention the error types
    all_suggestions = ' '.join(suggestions)
    assert "AttributeError" in all_suggestions
    assert "ZeroDivisionError" in all_suggestions


def test_viability_matrix_to_dict():
    """Test ViabilityMatrix serialization"""
    matrix = ViabilityMatrix(
        cost=CostEstimate(api_cost_usd=1.0),
        impact=ImpactEstimate(user_utility_level=ImpactLevel.MEDIUM),
        risk=RiskEstimate(risk_level=RiskLevel.LOW),
        proposal_title="Serialization Test",
        proposal_description="Test",
    )
    
    data = matrix.to_dict()
    
    # Verify structure
    assert "proposal_title" in data
    assert "cost" in data
    assert "impact" in data
    assert "risk" in data
    assert "roi" in data
    assert "viable" in data
    
    # Verify nested data
    assert "total_score" in data["cost"]
    assert "total_score" in data["impact"]
    assert "total_score" in data["risk"]
