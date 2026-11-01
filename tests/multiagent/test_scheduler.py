"""Tests for the shared multi-agent contracts and assignment policy."""
import pytest

from app.multiagent.model_registry import ModelProfile, ModelRegistry

from app.multiagent import (
    AgentProfile,
    CostBenefitScheduler,
    NoEligibleAgentError,
    TaskSpec,
)


def test_leader_and_workers_use_same_contract_and_role_is_task_scoped():
    task = TaskSpec(
        task_id="task-1",
        objective="Inspect the failing tests",
        required_tools=("repo.read", "pytest"),
        task_type="verification",
        acceptance_criteria=("Report exact command and result",),
    )
    agents = [
        AgentProfile(
            agent_id="leader",
            available_tools=("repo.read", "pytest", "browser"),
            estimated_cost=0.02,
            success_rates={"verification": 0.9},
        ),
        AgentProfile(
            agent_id="worker",
            available_tools=("repo.read", "pytest", "browser"),
            estimated_cost=0.03,
            success_rates={"verification": 0.8},
        ),
    ]

    assignment = CostBenefitScheduler().choose(task, agents, leader_id="leader")
    payload = assignment.to_dict()

    assert assignment.assigned_agent_id == "leader"
    assert assignment.assigned_role == "Verification"
    assert payload["required_tools"] == ["repo.read", "pytest"]
    assert payload["acceptance_criteria"] == ["Report exact command and result"]
    assert payload["leader_id"] == "leader"
    assert payload["required_model_provider"] is None


@pytest.mark.parametrize("task_type", ["red_team", "Red Team", "red-team", "blue_team", "BLUE TEAM"])
def test_red_blue_tasks_are_routed_only_to_venice_agents(task_type):
    task = TaskSpec(
        task_id="security-task",
        objective="Perform an authorized security review",
        task_type=task_type,
    )
    agents = [
        AgentProfile("corporate-model", estimated_cost=0.001, model_provider="openai"),
        AgentProfile("groq-agent", estimated_cost=0.001, model_provider="groq"),
        AgentProfile("venice-agent", estimated_cost=0.5, model_provider="Venice"),
    ]

    assignment = CostBenefitScheduler().choose(task, agents, leader_id="leader")

    assert assignment.assigned_agent_id == "venice-agent"
    assert assignment.required_model_provider == "venice"
    assert assignment.to_dict()["required_model_provider"] == "venice"


@pytest.mark.parametrize("task_type", ["red_team", "blue_team"])
def test_red_blue_tasks_fail_closed_when_no_venice_agent_is_available(task_type):
    task = TaskSpec(
        task_id="security-task",
        objective="Perform an authorized security review",
        task_type=task_type,
    )
    agents = [
        AgentProfile("groq-agent", model_provider="groq"),
        AgentProfile("offline-venice", status="offline", model_provider="venice"),
    ]

    with pytest.raises(NoEligibleAgentError, match="require an available Venice-configured agent"):
        CostBenefitScheduler().choose(task, agents, leader_id="leader")


def test_non_security_tasks_keep_normal_provider_selection():
    task = TaskSpec(
        task_id="general-task",
        objective="Summarize documentation",
        task_type="research",
    )
    agents = [
        AgentProfile("groq-agent", estimated_cost=0.2, model_provider="groq"),
        AgentProfile("venice-agent", estimated_cost=0.4, model_provider="venice"),
    ]

    assignment = CostBenefitScheduler().choose(task, agents, leader_id="leader")

    assert assignment.assigned_agent_id == "groq-agent"
    assert assignment.required_model_provider is None


def test_scheduler_filters_unavailable_capacity_tools_and_budget():
    task = TaskSpec(
        task_id="task-2",
        objective="Run isolated validation",
        required_tools=("sandbox.execute",),
        max_cost=0.10,
    )
    agents = [
        AgentProfile("offline", ("sandbox.execute",), status="offline", estimated_cost=0.01),
        AgentProfile("busy", ("sandbox.execute",), active_tasks=1, concurrency_limit=1),
        AgentProfile("missing-tool", ("repo.read",), estimated_cost=0.01),
        AgentProfile("over-budget", ("sandbox.execute",), estimated_cost=0.11),
    ]

    with pytest.raises(NoEligibleAgentError):
        CostBenefitScheduler().choose(task, agents, leader_id="leader")


def test_scheduler_prefers_success_adjusted_cost_benefit_and_is_deterministic():
    task = TaskSpec(
        task_id="task-3",
        objective="Research API compatibility",
        task_type="research",
        expected_value=10,
    )
    agents = [
        AgentProfile(
            "expensive-expert",
            estimated_cost=2.0,
            success_rates={"research": 0.99},
        ),
        AgentProfile(
            "cheap-reliable",
            estimated_cost=0.2,
            success_rates={"research": 0.9},
        ),
        AgentProfile(
            "cheap-reliable-tie",
            estimated_cost=0.2,
            success_rates={"research": 0.9},
        ),
    ]

    assignment = CostBenefitScheduler().choose(task, agents, leader_id="leader")
    assert assignment.assigned_agent_id == "cheap-reliable"
    assert assignment.estimated_success_probability == pytest.approx(0.9)


def test_contract_rejects_invalid_values():
    with pytest.raises(ValueError):
        AgentProfile("agent", success_rates={"coding": 1.5})
    with pytest.raises(ValueError):
        TaskSpec(task_id="x", objective="y", risk_level="unknown")



def test_scheduler_uses_registry_to_match_model_capabilities_and_modalities():
    registry = ModelRegistry([
        ModelProfile(
            model_id="text-model",
            provider_id="provider-a",
            runtime_kind="remote_api",
            capabilities={"chat", "tools"},
            modalities={"text"},
        ),
        ModelProfile(
            model_id="vision-model",
            provider_id="provider-b",
            runtime_kind="local_runtime",
            capabilities={"chat", "vision"},
            modalities={"text", "image"},
        ),
    ])
    task = TaskSpec(
        task_id="inspect-image",
        objective="Analyze the supplied image",
        required_model_capabilities=("vision",),
        required_modalities=("text", "image"),
    )
    agents = [
        AgentProfile("text-agent", model_provider="provider-a", model_id="text-model"),
        AgentProfile("vision-agent", model_provider="provider-b", model_id="vision-model"),
    ]

    assignment = CostBenefitScheduler(model_registry=registry).choose(
        task, agents, leader_id="leader"
    )

    assert assignment.assigned_agent_id == "vision-agent"
    assert assignment.selected_model_id == "vision-model"
    assert assignment.to_dict()["selected_model_id"] == "vision-model"


def test_scheduler_fails_closed_when_task_requires_model_registry_but_none_is_configured():
    task = TaskSpec(
        task_id="vision-task",
        objective="Analyze image",
        required_model_capabilities=("vision",),
        required_modalities=("text", "image"),
    )
    with pytest.raises(NoEligibleAgentError, match="no ModelRegistry is configured"):
        CostBenefitScheduler().choose(
            task,
            [AgentProfile("agent", model_provider="provider", model_id="vision-model")],
            leader_id="leader",
        )


def test_scheduler_excludes_unavailable_or_provider_mismatched_model_profiles():
    registry = ModelRegistry([
        ModelProfile(
            model_id="offline",
            provider_id="provider-a",
            runtime_kind="remote_api",
            available=False,
        ),
        ModelProfile(
            model_id="other-provider",
            provider_id="provider-b",
            runtime_kind="remote_api",
        ),
    ])
    task = TaskSpec(task_id="general", objective="Do work")
    agents = [
        AgentProfile("offline-agent", model_provider="provider-a", model_id="offline"),
        AgentProfile("mismatch-agent", model_provider="provider-a", model_id="other-provider"),
    ]

    with pytest.raises(NoEligibleAgentError):
        CostBenefitScheduler(model_registry=registry).choose(
            task, agents, leader_id="leader"
        )


def test_scheduler_keeps_legacy_agent_selection_without_model_registry():
    task = TaskSpec(task_id="legacy", objective="Continue legacy scheduling")
    assignment = CostBenefitScheduler().choose(
        task, [AgentProfile("legacy-agent", model_provider="provider-a")],
        leader_id="leader",
    )
    assert assignment.assigned_agent_id == "legacy-agent"
    assert assignment.selected_model_id is None
