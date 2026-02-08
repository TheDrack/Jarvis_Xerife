# -*- coding: utf-8 -*-
"""Viability Matrix and ROI models for Xerife Strategist module"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class RiskLevel(str, Enum):
    """Risk levels for technical changes"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImpactLevel(str, Enum):
    """Impact levels for improvements"""
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CostEstimate:
    """Estimated costs for implementing a proposal"""
    
    # Token consumption
    api_tokens: int = 0  # Estimated tokens for LLM API calls
    api_cost_usd: float = 0.0  # Estimated cost in USD
    
    # Development complexity
    code_complexity: str = "simple"  # simple, moderate, complex
    lines_of_code_estimate: int = 0
    
    # Time estimates
    ci_cd_time_minutes: int = 0
    development_time_hours: float = 0.0
    
    def total_cost_score(self) -> float:
        """Calculate total cost score (0-10 scale, higher = more expensive)"""
        score = 0.0
        
        # API cost contribution (0-3)
        if self.api_cost_usd > 10:
            score += 3
        elif self.api_cost_usd > 5:
            score += 2
        elif self.api_cost_usd > 1:
            score += 1
        
        # Complexity contribution (0-3)
        complexity_scores = {"simple": 0, "moderate": 1.5, "complex": 3}
        score += complexity_scores.get(self.code_complexity, 0)
        
        # Time contribution (0-4)
        total_hours = self.development_time_hours + (self.ci_cd_time_minutes / 60)
        if total_hours > 8:
            score += 4
        elif total_hours > 4:
            score += 3
        elif total_hours > 2:
            score += 2
        elif total_hours > 1:
            score += 1
        
        return min(score, 10.0)


@dataclass
class ImpactEstimate:
    """Estimated impact/benefits of implementing a proposal"""
    
    # Performance improvements
    performance_gain_percent: float = 0.0
    
    # Error reduction
    error_reduction_percent: float = 0.0
    potential_bugs_prevented: int = 0
    
    # User value
    user_utility_level: ImpactLevel = ImpactLevel.MINIMAL
    
    # System improvements
    technical_debt_reduction: bool = False
    code_maintainability_improvement: bool = False
    
    def total_impact_score(self) -> float:
        """Calculate total impact score (0-10 scale, higher = more beneficial)"""
        score = 0.0
        
        # Performance contribution (0-3)
        if self.performance_gain_percent > 50:
            score += 3
        elif self.performance_gain_percent > 20:
            score += 2
        elif self.performance_gain_percent > 5:
            score += 1
        
        # Error reduction contribution (0-2)
        if self.error_reduction_percent > 50 or self.potential_bugs_prevented > 5:
            score += 2
        elif self.error_reduction_percent > 20 or self.potential_bugs_prevented > 2:
            score += 1
        
        # User utility contribution (0-3)
        utility_scores = {
            ImpactLevel.MINIMAL: 0,
            ImpactLevel.LOW: 0.5,
            ImpactLevel.MEDIUM: 1.5,
            ImpactLevel.HIGH: 2.5,
            ImpactLevel.CRITICAL: 3
        }
        score += utility_scores.get(self.user_utility_level, 0)
        
        # System improvement contribution (0-2)
        if self.technical_debt_reduction:
            score += 1
        if self.code_maintainability_improvement:
            score += 1
        
        return min(score, 10.0)


@dataclass
class RiskEstimate:
    """Estimated technical risks of implementing a proposal"""
    
    risk_level: RiskLevel = RiskLevel.LOW
    breaks_legacy_systems: bool = False
    introduces_new_dependencies: bool = False
    security_concerns: bool = False
    backwards_incompatible: bool = False
    
    # Risk descriptions
    risk_description: str = ""
    mitigation_strategy: str = ""
    
    def total_risk_score(self) -> float:
        """Calculate total risk score (0-10 scale, higher = more risky)"""
        score = 0.0
        
        # Base risk level (0-4)
        risk_scores = {
            RiskLevel.LOW: 0.5,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4
        }
        score += risk_scores.get(self.risk_level, 0)
        
        # Additional risk factors (each adds points)
        if self.breaks_legacy_systems:
            score += 2
        if self.introduces_new_dependencies:
            score += 1
        if self.security_concerns:
            score += 2
        if self.backwards_incompatible:
            score += 1
        
        return min(score, 10.0)


@dataclass
class ViabilityMatrix:
    """
    Comprehensive viability analysis for autonomous improvement proposals.
    Used by Xerife Strategist to determine if an idea should be pursued.
    """
    
    # Core estimates
    cost: CostEstimate
    impact: ImpactEstimate
    risk: RiskEstimate
    
    # Metadata
    proposal_id: str = ""
    proposal_title: str = ""
    proposal_description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Decision tracking
    approved: bool = False
    rejection_reason: str = ""
    
    def calculate_roi(self) -> float:
        """
        Calculate ROI score: (Impact - Risk) / Cost
        Higher is better. Negative means costs/risks outweigh benefits.
        """
        cost_score = max(self.cost.total_cost_score(), 0.1)  # Avoid division by zero
        impact_score = self.impact.total_impact_score()
        risk_score = self.risk.total_risk_score()
        
        # ROI = (Benefit - Risk) / Cost
        roi = (impact_score - risk_score) / cost_score
        return roi
    
    def is_viable(self, min_roi_threshold: float = 0.5) -> bool:
        """
        Determine if proposal is viable based on ROI and safety thresholds
        
        Args:
            min_roi_threshold: Minimum ROI required for approval (default: 0.5)
        
        Returns:
            True if proposal meets viability criteria
        """
        roi = self.calculate_roi()
        
        # Reject if ROI is too low
        if roi < min_roi_threshold:
            return False
        
        # Reject if risk is critical or high without sufficient impact
        if self.risk.risk_level == RiskLevel.CRITICAL:
            return False
        
        if self.risk.risk_level == RiskLevel.HIGH:
            if self.impact.user_utility_level not in [ImpactLevel.HIGH, ImpactLevel.CRITICAL]:
                return False
        
        # Reject if has security concerns without mitigation
        if self.risk.security_concerns and not self.risk.mitigation_strategy:
            return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "proposal_id": self.proposal_id,
            "proposal_title": self.proposal_title,
            "proposal_description": self.proposal_description,
            "created_at": self.created_at.isoformat(),
            "cost": {
                "api_tokens": self.cost.api_tokens,
                "api_cost_usd": self.cost.api_cost_usd,
                "code_complexity": self.cost.code_complexity,
                "lines_of_code_estimate": self.cost.lines_of_code_estimate,
                "ci_cd_time_minutes": self.cost.ci_cd_time_minutes,
                "development_time_hours": self.cost.development_time_hours,
                "total_score": self.cost.total_cost_score(),
            },
            "impact": {
                "performance_gain_percent": self.impact.performance_gain_percent,
                "error_reduction_percent": self.impact.error_reduction_percent,
                "potential_bugs_prevented": self.impact.potential_bugs_prevented,
                "user_utility_level": self.impact.user_utility_level.value,
                "technical_debt_reduction": self.impact.technical_debt_reduction,
                "code_maintainability_improvement": self.impact.code_maintainability_improvement,
                "total_score": self.impact.total_impact_score(),
            },
            "risk": {
                "risk_level": self.risk.risk_level.value,
                "breaks_legacy_systems": self.risk.breaks_legacy_systems,
                "introduces_new_dependencies": self.risk.introduces_new_dependencies,
                "security_concerns": self.risk.security_concerns,
                "backwards_incompatible": self.risk.backwards_incompatible,
                "risk_description": self.risk.risk_description,
                "mitigation_strategy": self.risk.mitigation_strategy,
                "total_score": self.risk.total_risk_score(),
            },
            "roi": self.calculate_roi(),
            "viable": self.is_viable(),
            "approved": self.approved,
            "rejection_reason": self.rejection_reason,
        }
