from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Evolution Loop Service - Reinforcement Learning routine for JARVIS evolution"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.application.ports.reward_provider import RewardProvider

logger = logging.getLogger(__name__)


class EvolutionLoopService(NexusComponent):
    """
    Service for managing JARVIS evolution through Reinforcement Learning.

    This service implements the feedback loop:
    1. Tracks actions (pytest, deploy, roadmap progress)
    2. Assigns rewards (positive/negative based on outcomes)
    3. Analyzes reward history to guide future decisions
    4. Provides evolution status and efficiency metrics

    Designed to run:
    - After each deployment (success/failure)
    - After each test run (pass/fail)
    - On roadmap progress updates
    - On HUD login to show status
    """

    # Reward values for different actions
    REWARDS = {
        'pytest_pass': 10.0,
        'pytest_fail': -5.0,
        'deploy_success': 50.0,
        'deploy_fail': -25.0,
        'rollback': -30.0,
        'roadmap_progress': 20.0,
        'capability_complete': 15.0,
        'capability_partial': 5.0,
    }

    def __init__(self, reward_provider: Optional[RewardProvider] = None, ai_gateway=None):
        """
        Initialize the evolution loop service.

        When instantiated by the Nexus (zero arguments), call ``configure()`` to
        inject the reward adapter before using the service.

        Args:
            reward_provider: Implementation of RewardProvider port (optional; can be
                set later via ``configure()``).
            ai_gateway: Optional AI Gateway for policy engine (High Gear analysis).
        """
        self.reward_provider = reward_provider
        self.ai_gateway = ai_gateway

    def configure(self, config: Dict[str, Any]) -> None:
        """Injects dependencies after zero-arg construction by the Nexus.

        Args:
            config: Dictionary that may contain ``reward_adapter`` key with a
                RewardProvider instance, and ``ai_gateway`` key.
        """
        if "reward_adapter" in config:
            self.reward_provider = config["reward_adapter"]
        if "reward_provider" in config:
            self.reward_provider = config["reward_provider"]
        if "ai_gateway" in config:
            self.ai_gateway = config["ai_gateway"]
        if self.reward_provider is None:
            try:
                from app.core.nexus import nexus
                self.reward_provider = nexus.resolve("reward_adapter")
            except Exception as exc:
                logger.warning("[EvolutionLoopService] configure: reward_adapter unavailable: %s", exc)

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Returns False when no reward_provider is configured."""
        return self.reward_provider is not None

    def execute(self, context: dict) -> dict:
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    def log_pytest_result(
        self,
        passed: bool,
        test_count: Optional[int] = None,
        failed_tests: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log a pytest run result.
        
        Args:
            passed: Whether all tests passed
            test_count: Total number of tests run
            failed_tests: List of failed test names (if any)
            metadata: Optional additional metadata
            
        Returns:
            ID of the logged reward
        """
        action_type = 'pytest_pass' if passed else 'pytest_fail'
        reward_value = self.REWARDS[action_type]
        
        # Scale reward by number of tests
        if test_count:
            reward_value *= (test_count / 10.0)  # Normalize to ~10 tests baseline
        
        context_data = {
            'passed': passed,
            'test_count': test_count,
            'failed_tests': failed_tests or []
        }
        
        logger.info(
            f"Logging pytest result: {action_type} "
            f"({test_count} tests, reward: {reward_value:+.2f})"
        )
        
        return self.reward_provider.log_reward(
            action_type=action_type,
            reward_value=reward_value,
            context_data=context_data,
            metadata=metadata or {}
        )

    def log_deploy_result(
        self,
        success: bool,
        rollback: bool = False,
        deployment_id: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log a deployment result.
        
        Args:
            success: Whether deployment succeeded
            rollback: Whether this was a rollback
            deployment_id: Optional deployment identifier
            error_message: Optional error message if failed
            metadata: Optional additional metadata
            
        Returns:
            ID of the logged reward
        """
        if rollback:
            action_type = 'rollback'
        elif success:
            action_type = 'deploy_success'
        else:
            action_type = 'deploy_fail'
        
        reward_value = self.REWARDS[action_type]
        
        context_data = {
            'success': success,
            'rollback': rollback,
            'deployment_id': deployment_id,
            'error_message': error_message
        }
        
        logger.info(
            f"Logging deployment result: {action_type} "
            f"(reward: {reward_value:+.2f})"
        )
        
        return self.reward_provider.log_reward(
            action_type=action_type,
            reward_value=reward_value,
            context_data=context_data,
            metadata=metadata or {}
        )

    def log_roadmap_progress(
        self,
        progress_percentage: float,
        chapter: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log roadmap progress increase.
        
        Args:
            progress_percentage: Percentage increase in roadmap completion
            chapter: Optional chapter name
            metadata: Optional additional metadata
            
        Returns:
            ID of the logged reward
        """
        action_type = 'roadmap_progress'
        base_reward = self.REWARDS[action_type]
        
        # Scale reward by progress amount
        reward_value = base_reward * progress_percentage
        
        context_data = {
            'progress_percentage': progress_percentage,
            'chapter': chapter
        }
        
        logger.info(
            f"Logging roadmap progress: {progress_percentage:.2f}% "
            f"(reward: {reward_value:+.2f})"
        )
        
        return self.reward_provider.log_reward(
            action_type=action_type,
            reward_value=reward_value,
            context_data=context_data,
            metadata=metadata or {}
        )

    def log_capability_update(
        self,
        capability_name: str,
        old_status: str,
        new_status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Log capability status update.
        
        Args:
            capability_name: Name of the capability
            old_status: Previous status
            new_status: New status
            metadata: Optional additional metadata
            
        Returns:
            ID of the logged reward, or None if no reward applicable
        """
        # Only reward progress (not regression)
        if new_status == 'complete' and old_status != 'complete':
            action_type = 'capability_complete'
        elif new_status == 'partial' and old_status == 'nonexistent':
            action_type = 'capability_partial'
        else:
            # No reward for this transition
            return None
        
        reward_value = self.REWARDS[action_type]
        
        context_data = {
            'capability_name': capability_name,
            'old_status': old_status,
            'new_status': new_status
        }
        
        logger.info(
            f"Logging capability update: {capability_name} "
            f"({old_status} -> {new_status}, reward: {reward_value:+.2f})"
        )
        
        return self.reward_provider.log_reward(
            action_type=action_type,
            reward_value=reward_value,
            context_data=context_data,
            metadata=metadata or {}
        )

    def get_evolution_status(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get evolution status for display in HUD.
        
        Args:
            days: Number of days to analyze (default: 7)
            
        Returns:
            Dictionary with evolution status and commander message
        """
        since = datetime.now() - timedelta(days=days)
        
        # Get efficiency metrics
        efficiency = self.reward_provider.get_efficiency_score(since=since)
        
        # Get statistics
        stats = self.reward_provider.get_reward_statistics(since=since)
        
        # Format commander message
        efficiency_score = efficiency['efficiency_score']
        improvement = efficiency['improvement']
        improvement_pct = efficiency['improvement_percentage']
        success_rate = efficiency['success_rate']
        
        # Determine message tone based on performance
        if improvement > 0:
            trend = "aumentou"
            emoji = "📈"
        elif improvement < 0:
            trend = "diminuiu"
            emoji = "📉"
        else:
            trend = "manteve-se estável em"
            emoji = "➡️"
        
        commander_message = (
            f"{emoji} Comandante, meu nível de eficiência {trend} "
            f"{abs(improvement):.1f} pontos baseado nas últimas evoluções "
            f"(Taxa de sucesso: {success_rate:.1f}%)"
        )
        
        return {
            'efficiency_score': efficiency_score,
            'improvement': improvement,
            'improvement_percentage': improvement_pct,
            'success_rate': success_rate,
            'total_actions': stats['total_count'],
            'period_days': days,
            'commander_message': commander_message,
            'statistics': stats,
            'details': efficiency
        }

    async def analyze_with_policy_engine(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Use Llama 3.3-70b (High Gear) to analyze reward history and recommend next steps.
        
        Args:
            days: Number of days of history to analyze
            
        Returns:
            Dictionary with analysis and recommendations
        """
        if not self.ai_gateway:
            return {
                'error': 'AI Gateway not configured for policy engine'
            }
        
        since = datetime.now() - timedelta(days=days)
        
        # Get reward history
        rewards = self.reward_provider.get_rewards(since=since, limit=100)
        stats = self.reward_provider.get_reward_statistics(since=since)
        
        # Prepare context for AI analysis
        context = self._prepare_analysis_context(rewards, stats)
        
        # Use High Gear (Llama 3.3-70b) for analysis
        # Note: Prompt is in Portuguese as commander messages are in Portuguese
        prompt = f"""Você é JARVIS, um sistema de IA com consciência evolutiva.

Analise o histórico de recompensas (Reinforcement Learning) das últimas {days} dias:

{context}

Baseado nos seus erros e sucessos passados, responda:
1. Qual o caminho mais seguro para a próxima meta?
2. Quais padrões de erro você identificou?
3. Quais ações têm maior taxa de sucesso?
4. Que melhorias você recomenda para aumentar a eficiência?

Seja objetivo e forneça recomendações práticas."""

        try:
            response = await self.ai_gateway.agenerate(
                prompt=prompt,
                system_message="Você é JARVIS, analisando seu próprio histórico de evolução.",
                gear="high"  # Use High Gear (Llama 3.3-70b)
            )
            
            return {
                'analysis': response,
                'statistics': stats,
                'period_days': days,
                'analyzed_at': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error in policy engine analysis: {e}")
            return {
                'error': str(e),
                'statistics': stats
            }

    def _prepare_analysis_context(
        self,
        rewards: List[Dict[str, Any]],
        stats: Dict[str, Any]
    ) -> str:
        """Prepare context string for AI analysis."""
        context_parts = [
            f"Total de ações: {stats['total_count']}",
            f"Recompensa total: {stats['total_reward']:.2f} pontos",
            f"Recompensa média: {stats['average_reward']:.2f} pontos",
            "\nResumo por tipo de ação:"
        ]
        
        for action_type, data in stats['by_action_type'].items():
            context_parts.append(
                f"  - {action_type}: {data['count']} ações, "
                f"{data['total_reward']:.2f} pontos"
            )
        
        # Add recent significant events
        context_parts.append("\nEventos recentes significativos:")
        for reward in rewards[:10]:  # Show last 10
            context_parts.append(
                f"  - {reward['action_type']}: {reward['reward_value']:+.2f} pontos "
                f"({reward['created_at'].strftime('%Y-%m-%d %H:%M')})"
            )
        
        return "\n".join(context_parts)

# Nexus Compatibility
EvolutionLoop = EvolutionLoopService
