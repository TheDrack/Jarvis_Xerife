from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Reward Adapter - Database implementation of RewardProvider port"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.application.ports.reward_provider import RewardProvider
from app.domain.models.evolution_reward import EvolutionReward

logger = logging.getLogger(__name__)


class RewardAdapter(RewardProvider):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    """
    Database implementation of the RewardProvider port.
    
    Uses SQLModel for ORM and supports any database backend
    configured via the SQLAlchemy engine.
    """

    def __init__(self, engine):
        """
        Initialize the reward adapter.
        
        Args:
            engine: SQLAlchemy engine instance
        """
        self.engine = engine
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Ensure the evolution_rewards table exists."""
        try:
            from sqlmodel import SQLModel
            SQLModel.metadata.create_all(self.engine, tables=[EvolutionReward.__table__])
            logger.info("Evolution rewards table verified/created")
        except Exception as e:
            logger.error(f"Error ensuring evolution_rewards table exists: {e}")

    def log_reward(
        self,
        action_type: str,
        reward_value: float,
        context_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log a reward event to the database.
        
        Args:
            action_type: Type of action (e.g., 'pytest_pass', 'deploy_success')
            reward_value: Reward points (positive for success, negative for failure)
            context_data: Optional context about the action
            metadata: Optional additional metadata
            
        Returns:
            ID of the logged reward
        """
        with Session(self.engine) as session:
            reward = EvolutionReward(
                action_type=action_type,
                reward_value=reward_value,
                context_data=context_data or {},
                meta_data=metadata or {},
                created_at=datetime.now()
            )
            session.add(reward)
            session.commit()
            session.refresh(reward)
            
            logger.info(
                f"Logged reward: {action_type} = {reward_value:+.2f} points "
                f"(ID: {reward.id})"
            )
            return reward.id

    def get_rewards(
        self,
        action_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve rewards based on filters.
        
        Args:
            action_type: Optional filter by action type
            since: Optional filter by timestamp
            limit: Optional limit on number of results
            
        Returns:
            List of reward dictionaries
        """
        with Session(self.engine) as session:
            statement = select(EvolutionReward)
            
            # Apply filters
            if action_type:
                statement = statement.where(EvolutionReward.action_type == action_type)
            if since:
                statement = statement.where(EvolutionReward.created_at >= since)
            
            # Order by most recent first
            statement = statement.order_by(EvolutionReward.created_at.desc())
            
            # Apply limit
            if limit:
                statement = statement.limit(limit)
            
            results = session.exec(statement).all()
            
            return [
                {
                    'id': r.id,
                    'action_type': r.action_type,
                    'reward_value': r.reward_value,
                    'context_data': r.context_data,
                    'meta_data': r.meta_data,
                    'created_at': r.created_at
                }
                for r in results
            ]

    def get_total_reward(
        self,
        action_type: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> float:
        """
        Calculate total reward points.
        
        Args:
            action_type: Optional filter by action type
            since: Optional filter by timestamp
            
        Returns:
            Sum of reward values
        """
        with Session(self.engine) as session:
            statement = select(func.sum(EvolutionReward.reward_value))
            
            # Apply filters
            if action_type:
                statement = statement.where(EvolutionReward.action_type == action_type)
            if since:
                statement = statement.where(EvolutionReward.created_at >= since)
            
            result = session.exec(statement).first()
            return float(result) if result else 0.0

    def get_reward_statistics(
        self,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get statistical summary of rewards.
        
        Args:
            since: Optional filter by timestamp
            
        Returns:
            Dictionary with statistics
        """
        with Session(self.engine) as session:
            # Get total counts and values
            statement = select(
                func.count(EvolutionReward.id),
                func.sum(EvolutionReward.reward_value),
                func.avg(EvolutionReward.reward_value),
                func.max(EvolutionReward.reward_value),
                func.min(EvolutionReward.reward_value)
            )
            
            if since:
                statement = statement.where(EvolutionReward.created_at >= since)
            
            result = session.exec(statement).first()
            count, total, avg, max_val, min_val = result if result else (0, 0, 0, 0, 0)
            
            # Get counts by action type
            type_statement = select(
                EvolutionReward.action_type,
                func.count(EvolutionReward.id),
                func.sum(EvolutionReward.reward_value)
            ).group_by(EvolutionReward.action_type)
            
            if since:
                type_statement = type_statement.where(EvolutionReward.created_at >= since)
            
            type_results = session.exec(type_statement).all()
            
            by_type = {
                action_type: {
                    'count': count,
                    'total_reward': float(total) if total else 0.0
                }
                for action_type, count, total in type_results
            }
            
            return {
                'total_count': count or 0,
                'total_reward': float(total) if total else 0.0,
                'average_reward': float(avg) if avg else 0.0,
                'max_reward': float(max_val) if max_val else 0.0,
                'min_reward': float(min_val) if min_val else 0.0,
                'by_action_type': by_type
            }

    def get_efficiency_score(
        self,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate efficiency score based on reward history.
        
        Args:
            since: Optional filter by timestamp
            
        Returns:
            Dictionary with efficiency metrics and trends
        """
        # If no time filter, default to last 7 days
        if not since:
            since = datetime.now() - timedelta(days=7)
        
        # Get current period stats
        current_stats = self.get_reward_statistics(since=since)
        
        # Get previous period stats (same duration, but before 'since')
        duration = datetime.now() - since
        previous_since = since - duration
        previous_stats = self.get_reward_statistics(since=previous_since)
        previous_until = since  # Previous period ends where current begins
        
        # Calculate previous period total with proper filtering
        with Session(self.engine) as session:
            statement = select(func.sum(EvolutionReward.reward_value)).where(
                EvolutionReward.created_at >= previous_since,
                EvolutionReward.created_at < previous_until
            )
            previous_total = session.exec(statement).first()
            previous_total = float(previous_total) if previous_total else 0.0
        
        # Calculate improvement
        current_total = current_stats['total_reward']
        improvement = current_total - previous_total
        improvement_percentage = (
            (improvement / abs(previous_total) * 100) 
            if previous_total != 0 
            else 0.0
        )
        
        # Calculate success rate (positive rewards vs total)
        positive_count = sum(
            stats['count'] 
            for action, stats in current_stats['by_action_type'].items()
            if stats['total_reward'] > 0
        )
        total_count = current_stats['total_count']
        success_rate = (positive_count / total_count * 100) if total_count > 0 else 0.0
        
        return {
            'efficiency_score': current_total,
            'improvement': improvement,
            'improvement_percentage': improvement_percentage,
            'success_rate': success_rate,
            'total_actions': total_count,
            'period_days': duration.days,
            'current_period': current_stats,
            'previous_period_total': previous_total
        }
