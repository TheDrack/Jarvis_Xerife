# -*- coding: utf-8 -*-
"""Tests for Evolution Loop Service and Reinforcement Learning System"""

import pytest
from datetime import datetime, timedelta
from sqlmodel import create_engine, Session, SQLModel

from app.domain.models.evolution_reward import EvolutionReward
from app.adapters.infrastructure.reward_adapter import RewardAdapter
from app.application.services.evolution_loop import EvolutionLoopService


@pytest.fixture
def test_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def reward_adapter(test_engine):
    """Create a reward adapter with test database."""
    return RewardAdapter(engine=test_engine)


@pytest.fixture
def evolution_service(reward_adapter):
    """Create an evolution loop service for testing."""
    return EvolutionLoopService(reward_provider=reward_adapter)


class TestEvolutionRewardModel:
    """Test the EvolutionReward domain model."""
    
    def test_create_reward(self, test_engine):
        """Test creating a reward entry."""
        with Session(test_engine) as session:
            reward = EvolutionReward(
                action_type="pytest_pass",
                reward_value=10.0,
                context_data={"test_count": 5},
                metadata={"user_id": "test_user"}
            )
            session.add(reward)
            session.commit()
            session.refresh(reward)
            
            assert reward.id is not None
            assert reward.action_type == "pytest_pass"
            assert reward.reward_value == 10.0
            assert reward.context_data["test_count"] == 5
    
    def test_default_values(self, test_engine):
        """Test default values for reward fields."""
        with Session(test_engine) as session:
            reward = EvolutionReward(
                action_type="deploy_success",
                reward_value=50.0
            )
            session.add(reward)
            session.commit()
            session.refresh(reward)
            
            # Note: meta_data is used instead of metadata to avoid SQLAlchemy reserved word conflict
            assert reward.context_data == {}
            assert reward.meta_data == {}
            assert isinstance(reward.created_at, datetime)


class TestRewardAdapter:
    """Test the RewardAdapter implementation."""
    
    def test_log_reward(self, reward_adapter):
        """Test logging a reward."""
        reward_id = reward_adapter.log_reward(
            action_type="pytest_pass",
            reward_value=10.0,
            context_data={"test_count": 10},
            metadata={"session_id": "abc123"}
        )
        
        assert reward_id is not None
        assert isinstance(reward_id, int)
    
    def test_get_rewards(self, reward_adapter):
        """Test retrieving rewards."""
        # Log some rewards
        reward_adapter.log_reward("pytest_pass", 10.0)
        reward_adapter.log_reward("pytest_fail", -5.0)
        reward_adapter.log_reward("deploy_success", 50.0)
        
        # Get all rewards
        rewards = reward_adapter.get_rewards()
        assert len(rewards) == 3
        
        # Get rewards by action type
        test_rewards = reward_adapter.get_rewards(action_type="pytest_pass")
        assert len(test_rewards) == 1
        assert test_rewards[0]['action_type'] == "pytest_pass"
    
    def test_get_rewards_with_limit(self, reward_adapter):
        """Test getting rewards with limit."""
        for i in range(10):
            reward_adapter.log_reward("pytest_pass", 10.0)
        
        rewards = reward_adapter.get_rewards(limit=5)
        assert len(rewards) == 5
    
    def test_get_rewards_since(self, reward_adapter):
        """Test getting rewards since a specific time."""
        # Log a reward
        reward_adapter.log_reward("pytest_pass", 10.0)
        
        # Get rewards since future (should be empty)
        future = datetime.now() + timedelta(days=1)
        rewards = reward_adapter.get_rewards(since=future)
        assert len(rewards) == 0
        
        # Get rewards since past (should include the reward)
        past = datetime.now() - timedelta(days=1)
        rewards = reward_adapter.get_rewards(since=past)
        assert len(rewards) == 1
    
    def test_get_total_reward(self, reward_adapter):
        """Test calculating total reward."""
        reward_adapter.log_reward("pytest_pass", 10.0)
        reward_adapter.log_reward("pytest_pass", 15.0)
        reward_adapter.log_reward("pytest_fail", -5.0)
        
        total = reward_adapter.get_total_reward()
        assert total == 20.0
        
        # Total for specific action type
        total_pass = reward_adapter.get_total_reward(action_type="pytest_pass")
        assert total_pass == 25.0
    
    def test_get_reward_statistics(self, reward_adapter):
        """Test getting reward statistics."""
        reward_adapter.log_reward("pytest_pass", 10.0)
        reward_adapter.log_reward("pytest_pass", 20.0)
        reward_adapter.log_reward("pytest_fail", -5.0)
        reward_adapter.log_reward("deploy_success", 50.0)
        
        stats = reward_adapter.get_reward_statistics()
        
        assert stats['total_count'] == 4
        assert stats['total_reward'] == 75.0
        assert stats['average_reward'] == 18.75
        assert stats['max_reward'] == 50.0
        assert stats['min_reward'] == -5.0
        
        # Check by_action_type breakdown
        assert 'pytest_pass' in stats['by_action_type']
        assert stats['by_action_type']['pytest_pass']['count'] == 2
        assert stats['by_action_type']['pytest_pass']['total_reward'] == 30.0
    
    def test_get_efficiency_score(self, reward_adapter):
        """Test calculating efficiency score."""
        # Log some recent rewards
        reward_adapter.log_reward("pytest_pass", 10.0)
        reward_adapter.log_reward("deploy_success", 50.0)
        
        efficiency = reward_adapter.get_efficiency_score()
        
        assert 'efficiency_score' in efficiency
        assert 'improvement' in efficiency
        assert 'success_rate' in efficiency
        assert efficiency['efficiency_score'] == 60.0


class TestEvolutionLoopService:
    """Test the EvolutionLoopService."""
    
    def test_log_pytest_result_pass(self, evolution_service):
        """Test logging a passing pytest result."""
        reward_id = evolution_service.log_pytest_result(
            passed=True,
            test_count=10,
            metadata={"session": "test123"}
        )
        
        assert reward_id is not None
        
        # Verify reward was logged correctly
        rewards = evolution_service.reward_provider.get_rewards()
        assert len(rewards) == 1
        assert rewards[0]['action_type'] == 'pytest_pass'
        assert rewards[0]['reward_value'] > 0
    
    def test_log_pytest_result_fail(self, evolution_service):
        """Test logging a failing pytest result."""
        reward_id = evolution_service.log_pytest_result(
            passed=False,
            test_count=10,
            failed_tests=["test_example.py::test_function"]
        )
        
        assert reward_id is not None
        
        rewards = evolution_service.reward_provider.get_rewards()
        assert len(rewards) == 1
        assert rewards[0]['action_type'] == 'pytest_fail'
        assert rewards[0]['reward_value'] < 0
        assert len(rewards[0]['context_data']['failed_tests']) == 1
    
    def test_log_deploy_result_success(self, evolution_service):
        """Test logging a successful deployment."""
        reward_id = evolution_service.log_deploy_result(
            success=True,
            deployment_id="deploy-123"
        )
        
        assert reward_id is not None
        
        rewards = evolution_service.reward_provider.get_rewards()
        assert rewards[0]['action_type'] == 'deploy_success'
        assert rewards[0]['reward_value'] == 50.0
    
    def test_log_deploy_result_fail(self, evolution_service):
        """Test logging a failed deployment."""
        reward_id = evolution_service.log_deploy_result(
            success=False,
            error_message="Build failed"
        )
        
        rewards = evolution_service.reward_provider.get_rewards()
        assert rewards[0]['action_type'] == 'deploy_fail'
        assert rewards[0]['reward_value'] < 0
    
    def test_log_deploy_result_rollback(self, evolution_service):
        """Test logging a rollback."""
        reward_id = evolution_service.log_deploy_result(
            success=False,
            rollback=True
        )
        
        rewards = evolution_service.reward_provider.get_rewards()
        assert rewards[0]['action_type'] == 'rollback'
        assert rewards[0]['reward_value'] == -30.0
    
    def test_log_roadmap_progress(self, evolution_service):
        """Test logging roadmap progress."""
        reward_id = evolution_service.log_roadmap_progress(
            progress_percentage=5.0,
            chapter="CHAPTER_1"
        )
        
        assert reward_id is not None
        
        rewards = evolution_service.reward_provider.get_rewards()
        assert rewards[0]['action_type'] == 'roadmap_progress'
        # Reward should be scaled by percentage
        assert rewards[0]['reward_value'] > 0
    
    def test_log_capability_update_to_complete(self, evolution_service):
        """Test logging capability completion."""
        reward_id = evolution_service.log_capability_update(
            capability_name="Voice Recognition",
            old_status="partial",
            new_status="complete"
        )
        
        assert reward_id is not None
        
        rewards = evolution_service.reward_provider.get_rewards()
        assert rewards[0]['action_type'] == 'capability_complete'
        assert rewards[0]['reward_value'] == 15.0
    
    def test_log_capability_update_to_partial(self, evolution_service):
        """Test logging capability partial progress."""
        reward_id = evolution_service.log_capability_update(
            capability_name="AI Integration",
            old_status="nonexistent",
            new_status="partial"
        )
        
        assert reward_id is not None
        
        rewards = evolution_service.reward_provider.get_rewards()
        assert rewards[0]['action_type'] == 'capability_partial'
        assert rewards[0]['reward_value'] == 5.0
    
    def test_log_capability_update_no_reward(self, evolution_service):
        """Test that no reward is given for non-progress updates."""
        reward_id = evolution_service.log_capability_update(
            capability_name="Test Capability",
            old_status="complete",
            new_status="partial"
        )
        
        # Should return None for regression
        assert reward_id is None
        
        # No rewards should be logged
        rewards = evolution_service.reward_provider.get_rewards()
        assert len(rewards) == 0
    
    def test_get_evolution_status(self, evolution_service):
        """Test getting evolution status."""
        # Log some actions
        evolution_service.log_pytest_result(passed=True, test_count=10)
        evolution_service.log_deploy_result(success=True)
        evolution_service.log_roadmap_progress(progress_percentage=2.0)
        
        status = evolution_service.get_evolution_status(days=7)
        
        assert 'efficiency_score' in status
        assert 'improvement' in status
        assert 'success_rate' in status
        assert 'commander_message' in status
        assert 'statistics' in status
        
        # Success rate should be 100% (all positive actions)
        assert status['success_rate'] == 100.0
        
        # Commander message should include efficiency info
        assert 'Comandante' in status['commander_message']
        assert 'eficiência' in status['commander_message']
    
    def test_get_evolution_status_with_failures(self, evolution_service):
        """Test evolution status with both successes and failures."""
        # Log mixed results
        evolution_service.log_pytest_result(passed=True, test_count=5)
        evolution_service.log_pytest_result(passed=False, test_count=3)
        evolution_service.log_deploy_result(success=False)
        
        status = evolution_service.get_evolution_status(days=7)
        
        # Success rate should be less than 100%
        assert status['success_rate'] < 100.0
        assert status['total_actions'] == 3
    
    def test_prepare_analysis_context(self, evolution_service):
        """Test preparation of context for AI analysis."""
        # Log some rewards
        evolution_service.log_pytest_result(passed=True, test_count=10)
        evolution_service.log_deploy_result(success=True)
        
        rewards = evolution_service.reward_provider.get_rewards(limit=10)
        stats = evolution_service.reward_provider.get_reward_statistics()
        
        context = evolution_service._prepare_analysis_context(rewards, stats)
        
        assert "Total de ações:" in context
        assert "Recompensa total:" in context
        assert "pytest_pass" in context or "deploy_success" in context


class TestRewardValues:
    """Test reward value configurations."""
    
    def test_reward_constants(self):
        """Test that reward values are properly configured."""
        assert EvolutionLoopService.REWARDS['pytest_pass'] > 0
        assert EvolutionLoopService.REWARDS['pytest_fail'] < 0
        assert EvolutionLoopService.REWARDS['deploy_success'] > 0
        assert EvolutionLoopService.REWARDS['deploy_fail'] < 0
        assert EvolutionLoopService.REWARDS['rollback'] < 0
        assert EvolutionLoopService.REWARDS['roadmap_progress'] > 0
    
    def test_deploy_success_higher_than_pytest(self):
        """Test that deployment success is rewarded more than test pass."""
        assert (
            EvolutionLoopService.REWARDS['deploy_success'] > 
            EvolutionLoopService.REWARDS['pytest_pass']
        )
    
    def test_rollback_penalty_higher_than_deploy_fail(self):
        """Test that rollback has higher penalty than deploy fail."""
        assert (
            abs(EvolutionLoopService.REWARDS['rollback']) >= 
            abs(EvolutionLoopService.REWARDS['deploy_fail'])
        )
