from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Reward Provider Port - Interface for reward tracking in Reinforcement Learning"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional


class RewardProvider(NexusComponent, ABC):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """
    Port (interface) for the Reinforcement Learning reward system.
    
    This abstract interface defines the contract for logging and analyzing
    rewards in JARVIS's evolution system. Concrete implementations (adapters)
    can use different storage backends (PostgreSQL, SQLite, etc.).
    """

    @abstractmethod
    def log_reward(
        self,
        action_type: str,
        reward_value: float,
        context_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log a reward event.
        
        Args:
            action_type: Type of action (e.g., 'pytest_pass', 'deploy_success')
            reward_value: Reward points (positive for success, negative for failure)
            context_data: Optional context about the action
            metadata: Optional additional metadata
            
        Returns:
            ID of the logged reward
        """
        pass

    @abstractmethod
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
            since: Optional filter by timestamp (get rewards since this time)
            limit: Optional limit on number of results
            
        Returns:
            List of reward dictionaries
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def get_reward_statistics(
        self,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get statistical summary of rewards.
        
        Args:
            since: Optional filter by timestamp
            
        Returns:
            Dictionary with statistics (total, average, count by type, etc.)
        """
        pass

    @abstractmethod
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
        pass
