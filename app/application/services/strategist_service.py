# -*- coding: utf-8 -*-
"""
Xerife Strategist Service - Autonomous improvement proposal system with ROI analysis

This service enables Jarvis to propose and implement improvements autonomously,
but under strict cost-benefit and security filters.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.domain.models.viability import (
    CostEstimate,
    ImpactEstimate,
    ImpactLevel,
    RiskEstimate,
    RiskLevel,
    ViabilityMatrix,
)

logger = logging.getLogger(__name__)


class BudgetExceededException(Exception):
    """Exception raised when mission budget is exceeded"""
    
    def __init__(self, used: float, limit: float):
        self.used = used
        self.limit = limit
        message = f"Budget exceeded: ${used:.2f} used, limit is ${limit:.2f}"
        super().__init__(message)


class StrategistService:
    """
    Service for autonomous improvement proposals and RFC management.
    
    Features:
    - Business case ROI analysis before implementation
    - RFC generation for approved proposals
    - Budget tracking and caps per mission
    - Proposal archiving (approved/rejected)
    - Decision interface for human approval
    """
    
    def __init__(
        self,
        proposals_dir: Optional[Path] = None,
        default_budget_cap: float = 10.0,  # Default $10 per mission
        min_roi_threshold: float = 0.5,
    ):
        """
        Initialize the Strategist Service
        
        Args:
            proposals_dir: Directory for storing proposals (default: docs/proposals)
            default_budget_cap: Default maximum spend per mission in USD
            min_roi_threshold: Minimum ROI required for auto-approval
        """
        if proposals_dir:
            self.proposals_dir = Path(proposals_dir)
        else:
            # Default to docs/proposals in project root
            self.proposals_dir = Path(__file__).parent.parent.parent.parent / "docs" / "proposals"
        
        self.approved_dir = self.proposals_dir / "approved"
        self.rejected_dir = self.proposals_dir / "rejected"
        
        # Create directories if they don't exist
        self.approved_dir.mkdir(parents=True, exist_ok=True)
        self.rejected_dir.mkdir(parents=True, exist_ok=True)
        
        self.default_budget_cap = default_budget_cap
        self.min_roi_threshold = min_roi_threshold
        
        logger.info(f"Strategist initialized: proposals_dir={self.proposals_dir}, "
                   f"budget_cap=${default_budget_cap}, min_roi={min_roi_threshold}")
    
    def generate_viability_matrix(
        self,
        proposal_title: str,
        proposal_description: str,
        cost: CostEstimate,
        impact: ImpactEstimate,
        risk: RiskEstimate,
    ) -> ViabilityMatrix:
        """
        Generate a viability matrix for internal monologue decision-making
        
        Args:
            proposal_title: Title of the proposal
            proposal_description: Detailed description
            cost: Cost estimate
            impact: Impact estimate
            risk: Risk estimate
        
        Returns:
            ViabilityMatrix with ROI calculation
        """
        # Generate proposal ID from title
        proposal_id = self._generate_proposal_id(proposal_title)
        
        matrix = ViabilityMatrix(
            proposal_id=proposal_id,
            proposal_title=proposal_title,
            proposal_description=proposal_description,
            cost=cost,
            impact=impact,
            risk=risk,
        )
        
        # Determine viability
        is_viable = matrix.is_viable(self.min_roi_threshold)
        matrix.approved = is_viable
        
        if not is_viable:
            roi = matrix.calculate_roi()
            if roi < self.min_roi_threshold:
                matrix.rejection_reason = f"ROI too low: {roi:.2f} < {self.min_roi_threshold}"
            elif risk.risk_level == RiskLevel.CRITICAL:
                matrix.rejection_reason = "Risk level is CRITICAL"
            elif risk.security_concerns and not risk.mitigation_strategy:
                matrix.rejection_reason = "Security concerns without mitigation strategy"
            else:
                matrix.rejection_reason = "Failed viability criteria"
        
        logger.info(f"Viability matrix generated: {proposal_id}, ROI={matrix.calculate_roi():.2f}, "
                   f"Viable={is_viable}")
        
        return matrix
    
    def archive_proposal(self, matrix: ViabilityMatrix) -> Path:
        """
        Archive a proposal to approved or rejected directory
        
        Args:
            matrix: ViabilityMatrix to archive
        
        Returns:
            Path to archived file
        """
        # Determine target directory
        if matrix.approved:
            target_dir = self.approved_dir
            status = "approved"
        else:
            target_dir = self.rejected_dir
            status = "rejected"
        
        # Create filename
        filename = f"{matrix.proposal_id}.json"
        filepath = target_dir / filename
        
        # Save as JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(matrix.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Proposal archived: {filepath} (status={status})")
        return filepath
    
    def generate_rfc(self, matrix: ViabilityMatrix) -> Path:
        """
        Generate an RFC (Request for Comments) markdown file for approved proposals
        
        Args:
            matrix: Approved ViabilityMatrix
        
        Returns:
            Path to generated RFC file
        
        Raises:
            ValueError: If matrix is not approved
        """
        if not matrix.approved:
            raise ValueError("Cannot generate RFC for rejected proposal")
        
        # Generate RFC content
        rfc_number = self._get_next_rfc_number()
        rfc_filename = f"RFC-{rfc_number:04d}.md"
        rfc_path = self.proposals_dir / rfc_filename
        
        rfc_content = self._format_rfc(matrix, rfc_number)
        
        # Write RFC file
        with open(rfc_path, 'w', encoding='utf-8') as f:
            f.write(rfc_content)
        
        logger.info(f"RFC generated: {rfc_path}")
        return rfc_path
    
    def format_decision_prompt(self, matrix: ViabilityMatrix) -> str:
        """
        Format a decision prompt for user approval
        
        Args:
            matrix: ViabilityMatrix to present
        
        Returns:
            Formatted prompt string for the commander
        """
        roi = matrix.calculate_roi()
        cost_score = matrix.cost.total_cost_score()
        impact_score = matrix.impact.total_impact_score()
        risk_score = matrix.risk.total_risk_score()
        
        prompt = f"""
🎯 **Comandante, identifiquei uma oportunidade de melhoria com ROI {'positivo' if roi > 0 else 'negativo'}.**

**Proposta:** {matrix.proposal_title}
{matrix.proposal_description}

**Análise de Viabilidade:**
• ROI Score: {roi:.2f} (Impact-Risk/Cost = ({impact_score:.1f}-{risk_score:.1f})/{cost_score:.1f})
• Custo Estimado: ${matrix.cost.api_cost_usd:.2f} USD, {matrix.cost.development_time_hours:.1f}h dev, complexidade {matrix.cost.code_complexity}
• Benefício Esperado: {matrix.impact.user_utility_level.value} utilidade, {matrix.impact.performance_gain_percent:.0f}% perf, {matrix.impact.error_reduction_percent:.0f}% menos erros
• Risco Técnico: {matrix.risk.risk_level.value}
"""
        
        if matrix.risk.risk_description:
            prompt += f"  - {matrix.risk.risk_description}\n"
        
        if matrix.risk.mitigation_strategy:
            prompt += f"  - Mitigação: {matrix.risk.mitigation_strategy}\n"
        
        prompt += f"\n**Recomendação:** {'✅ APROVAR' if matrix.approved else '❌ REJEITAR'}"
        
        if matrix.rejection_reason:
            prompt += f" - {matrix.rejection_reason}"
        
        prompt += "\n\n**Posso prosseguir com a criação da branch e implementação?** (sim/não)"
        
        return prompt.strip()
    
    def check_budget(self, used_tokens: int, token_cost_per_1k: float, budget_cap: Optional[float] = None) -> Tuple[float, bool]:
        """
        Check if current token usage is within budget
        
        Args:
            used_tokens: Number of tokens used
            token_cost_per_1k: Cost per 1000 tokens in USD
            budget_cap: Budget cap in USD (uses default if not provided)
        
        Returns:
            Tuple of (current_cost_usd, is_within_budget)
        
        Raises:
            BudgetExceededException: If budget is exceeded
        """
        budget_cap = budget_cap or self.default_budget_cap
        current_cost = (used_tokens / 1000) * token_cost_per_1k
        
        is_within_budget = current_cost <= budget_cap
        
        if not is_within_budget:
            logger.warning(f"Budget exceeded: ${current_cost:.2f} > ${budget_cap:.2f}")
            raise BudgetExceededException(current_cost, budget_cap)
        
        logger.debug(f"Budget check: ${current_cost:.2f} / ${budget_cap:.2f}")
        return current_cost, is_within_budget
    
    def analyze_error_logs(self, error_logs: List[Dict[str, Any]]) -> List[str]:
        """
        Analyze error logs and propose preventive refactoring opportunities
        
        Args:
            error_logs: List of error log entries with 'error_message', 'count', etc.
        
        Returns:
            List of refactoring suggestions
        """
        suggestions = []
        
        # Group errors by type/pattern
        error_patterns = {}
        for log in error_logs:
            error_msg = log.get('error_message', '')
            error_type = log.get('error_type', 'unknown')
            count = log.get('count', 1)
            
            key = f"{error_type}:{error_msg[:50]}"
            if key not in error_patterns:
                error_patterns[key] = {'count': 0, 'examples': []}
            
            error_patterns[key]['count'] += count
            error_patterns[key]['examples'].append(error_msg)
        
        # Generate suggestions for frequent errors
        for pattern, data in error_patterns.items():
            if data['count'] >= 3:  # Threshold for refactoring suggestion
                suggestion = f"Refactoring oportunidade: '{pattern}' ocorreu {data['count']} vezes. " \
                           f"Considere adicionar validação ou tratamento específico."
                suggestions.append(suggestion)
        
        logger.info(f"Error log analysis: {len(suggestions)} refactoring suggestions generated")
        return suggestions
    
    def _generate_proposal_id(self, title: str) -> str:
        """Generate a unique proposal ID from title"""
        # Convert to lowercase, replace spaces with hyphens
        proposal_id = title.lower().replace(' ', '-')
        # Remove special characters
        proposal_id = ''.join(c for c in proposal_id if c.isalnum() or c == '-')
        # Add timestamp for uniqueness
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        return f"{proposal_id}-{timestamp}"
    
    def _get_next_rfc_number(self) -> int:
        """Get the next available RFC number"""
        existing_rfcs = list(self.proposals_dir.glob("RFC-*.md"))
        
        if not existing_rfcs:
            return 1
        
        # Extract numbers from existing RFCs
        numbers = []
        for rfc_path in existing_rfcs:
            try:
                # Extract number from RFC-XXXX.md
                num_str = rfc_path.stem.split('-')[1]
                numbers.append(int(num_str))
            except (IndexError, ValueError):
                continue
        
        return max(numbers) + 1 if numbers else 1
    
    def _format_rfc(self, matrix: ViabilityMatrix, rfc_number: int) -> str:
        """Format RFC markdown content"""
        rfc_content = f"""# RFC-{rfc_number:04d}: {matrix.proposal_title}

**Status:** Proposto  
**Data:** {matrix.created_at.strftime('%Y-%m-%d')}  
**Autor:** Jarvis (Xerife Strategist)  
**ROI Score:** {matrix.calculate_roi():.2f}

## Resumo

{matrix.proposal_description}

## Motivação

Esta proposta foi gerada pelo módulo Xerife Strategist após análise de viabilidade.

### Análise de Custos

- **Custo Estimado:** ${matrix.cost.api_cost_usd:.2f} USD
- **Tokens de API:** {matrix.cost.api_tokens} tokens
- **Complexidade de Código:** {matrix.cost.code_complexity}
- **Linhas de Código Estimadas:** {matrix.cost.lines_of_code_estimate}
- **Tempo de Desenvolvimento:** {matrix.cost.development_time_hours:.1f} horas
- **Tempo de CI/CD:** {matrix.cost.ci_cd_time_minutes} minutos
- **Score de Custo:** {matrix.cost.total_cost_score():.1f}/10

### Análise de Impacto

- **Ganho de Performance:** {matrix.impact.performance_gain_percent:.1f}%
- **Redução de Erros:** {matrix.impact.error_reduction_percent:.1f}%
- **Bugs Prevenidos:** {matrix.impact.potential_bugs_prevented}
- **Nível de Utilidade:** {matrix.impact.user_utility_level.value}
- **Redução de Débito Técnico:** {'Sim' if matrix.impact.technical_debt_reduction else 'Não'}
- **Melhoria de Manutenibilidade:** {'Sim' if matrix.impact.code_maintainability_improvement else 'Não'}
- **Score de Impacto:** {matrix.impact.total_impact_score():.1f}/10

### Análise de Riscos

- **Nível de Risco:** {matrix.risk.risk_level.value}
- **Quebra de Sistemas Legados:** {'Sim' if matrix.risk.breaks_legacy_systems else 'Não'}
- **Novas Dependências:** {'Sim' if matrix.risk.introduces_new_dependencies else 'Não'}
- **Preocupações de Segurança:** {'Sim' if matrix.risk.security_concerns else 'Não'}
- **Incompatibilidade Retroativa:** {'Sim' if matrix.risk.backwards_incompatible else 'Não'}
- **Score de Risco:** {matrix.risk.total_risk_score():.1f}/10

**Descrição do Risco:**  
{matrix.risk.risk_description or 'Nenhum risco significativo identificado.'}

**Estratégia de Mitigação:**  
{matrix.risk.mitigation_strategy or 'N/A'}

## Proposta Técnica

_[A ser preenchido durante a implementação]_

## Implementação

_[A ser preenchido durante a implementação]_

## Testes

_[A ser preenchido durante a implementação]_

## Alternativas Consideradas

_[A ser preenchido durante a discussão]_

## Decisão

**Aprovado por:** _[Aguardando aprovação do Comandante]_  
**Data da Decisão:** _[Pendente]_

## Referências

- Viability Matrix: `docs/proposals/approved/{matrix.proposal_id}.json`
"""
        return rfc_content
