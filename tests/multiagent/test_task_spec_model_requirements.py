"""Regression tests for TaskSpec model-requirement collection inputs."""
import pytest

from app.multiagent.contracts import TaskSpec


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("required_model_capabilities", "vision"),
        ("required_model_capabilities", b"vision"),
        ("required_modalities", "image"),
        ("required_modalities", b"image"),
    ],
)
def test_task_spec_rejects_scalar_model_requirement_strings(field_name, value):
    with pytest.raises(TypeError, match="not a string"):
        TaskSpec(
            task_id="task",
            objective="Validate model requirements",
            **{field_name: value},
        )


def test_task_spec_normalizes_model_requirement_iterables_to_immutable_tuples():
    capabilities = (item for item in ("vision", "tools"))
    modalities = ["text", "image"]

    task = TaskSpec(
        task_id="vision-task",
        objective="Analyze an image",
        required_model_capabilities=capabilities,
        required_modalities=modalities,
    )

    assert task.required_model_capabilities == ("vision", "tools")
    assert task.required_modalities == ("text", "image")
    assert isinstance(task.required_model_capabilities, tuple)
    assert isinstance(task.required_modalities, tuple)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("required_model_capabilities", ("vision", "")),
        ("required_model_capabilities", ("vision", 1)),
        ("required_modalities", ("text", None)),
        ("required_modalities", ("image", b"text")),
    ],
)
def test_task_spec_rejects_empty_or_non_string_model_requirement_labels(field_name, value):
    with pytest.raises(ValueError, match="only non-empty strings"):
        TaskSpec(
            task_id="task",
            objective="Validate model requirements",
            **{field_name: value},
        )
