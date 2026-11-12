import sys
from pathlib import Path
from types import SimpleNamespace

import yaml


def test_execute_initializes_missing_metadata(monkeypatch):
    # Keep this unit test independent from the optional LiteLLM package.
    fake_litellm = SimpleNamespace(
        completion=lambda **kwargs: SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="CONVERSA")
                )
            ]
        )
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    from app.domain.gears.cognitive_router import CognitiveRouter

    context = {"artifacts": {}}
    result = CognitiveRouter().execute(context)

    assert result is context
    assert context["metadata"] == {"marcha": "CONVERSA"}


def test_jarvis_chat_pipeline_declares_router_hint_path():
    pipeline_path = Path("config/pipelines/jarvis_chat.yml")
    config = yaml.safe_load(pipeline_path.read_text(encoding="utf-8"))

    assert (
        config["components"]["router"]["hint_path"]
        == "app/domain/gears/cognitive_router.py"
    )
