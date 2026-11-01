"""Regression tests for immutable agent/task string-collection contracts."""
import pytest

from app.multiagent.contracts import AgentProfile, TaskSpec


@pytest.mark.parametrize(
    "value",
    ["repo.read", b"repo.read"],
)
def test_agent_profile_rejects_scalar_available_tools(value):
    with pytest.raises(TypeError, match="not a string"):
        AgentProfile(agent_id="agent", available_tools=value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        (field_name, value)
        for field_name in (
            "required_tools",
            "constraints",
            "acceptance_criteria",
            "required_model_capabilities",
            "required_modalities",
        )
        for value in ("label", b"label")
    ],
)
def test_task_spec_rejects_scalar_string_collections(field_name, value):
    with pytest.raises(TypeError, match="not a string"):
        TaskSpec(
            task_id="task",
            objective="Validate contract collections",
            **{field_name: value},
        )


def test_agent_and_task_contracts_normalize_iterables_to_immutable_tuples():
    profile = AgentProfile(
        agent_id="agent",
        available_tools=["repo.read", "pytest"],
    )
    task = TaskSpec(
        task_id="vision-task",
        objective="Analyze an image",
        required_tools=["image.read"],
        constraints=(item for item in ("read-only", "bounded")),
        acceptance_criteria=["return evidence"],
        required_model_capabilities=(item for item in ("vision", "tools")),
        required_modalities=["text", "image"],
    )

    assert profile.available_tools == ("repo.read", "pytest")
    assert isinstance(profile.available_tools, tuple)
    assert task.required_tools == ("image.read",)
    assert task.constraints == ("read-only", "bounded")
    assert task.acceptance_criteria == ("return evidence",)
    assert task.required_model_capabilities == ("vision", "tools")
    assert task.required_modalities == ("text", "image")
    assert all(
        isinstance(value, tuple)
        for value in (
            task.required_tools,
            task.constraints,
            task.acceptance_criteria,
            task.required_model_capabilities,
            task.required_modalities,
        )
    )


@pytest.mark.parametrize(
    "value",
    [
        ("valid", ""),
        ("valid", 1),
        ("valid", None),
        ("valid", b"not-text"),
    ],
)
def test_agent_profile_rejects_invalid_tool_labels(value):
    with pytest.raises(ValueError, match="only non-empty strings"):
        AgentProfile(agent_id="agent", available_tools=value)


@pytest.mark.parametrize(
    "field_name",
    [
        "required_tools",
        "constraints",
        "acceptance_criteria",
        "required_model_capabilities",
        "required_modalities",
    ],
)
def test_task_spec_rejects_empty_and_non_string_labels(field_name):
    for value in (("valid", ""), ("valid", 1), ("valid", None), ("valid", b"not-text")):
        with pytest.raises(ValueError, match="only non-empty strings"):
            TaskSpec(
                task_id="task",
                objective="Validate contract labels",
                **{field_name: value},
            )
