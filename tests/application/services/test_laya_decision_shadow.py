"""Tests for the optional Laya decision adapter and shadow observer."""
from __future__ import annotations
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from app.adapters.infrastructure.intelligence.laya_decision_adapter import LayaDecisionAdapter, LayaDecisionError
from app.application.services.laya_decision_shadow import LayaDecisionShadowObserver

class _Response:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self, _limit): return json.dumps(self.payload).encode()

def test_laya_adapter_posts_typed_decision_request():
    captured = {}
    def opener(request, timeout):
        captured.update(url=request.full_url, timeout=timeout, body=json.loads(request.data),
                        authorization=request.get_header("Authorization"))
        return _Response({"answers": {"task_type": {"choice": "planning"}}})
    adapter = LayaDecisionAdapter("http://127.0.0.1:8000", api_key="secret", opener=opener)
    result = adapter.decide({"request": "plan this"}, {"task_type": {"type": "choice"}})
    assert captured["url"] == "http://127.0.0.1:8000/predict"
    assert captured["body"]["state"] == {"request": "plan this"}
    assert captured["authorization"] == "Bearer secret"
    assert result["answers"]["task_type"]["choice"] == "planning"

def test_laya_adapter_rejects_non_loopback_plain_http():
    with pytest.raises(ValueError, match="loopback"):
        LayaDecisionAdapter("http://192.168.1.10:8000")

def test_laya_adapter_rejects_malformed_response():
    class BadResponse(_Response):
        def read(self, _limit): return b"not-json"
    adapter = LayaDecisionAdapter("http://127.0.0.1:8000", opener=lambda *_a, **_k: BadResponse({}))
    with pytest.raises(LayaDecisionError, match="invalid JSON"):
        adapter.decide({"request": "test"}, {"task_type": {"type": "choice"}})

def test_shadow_observer_records_prediction_without_exposing_input():
    sink, engine = MagicMock(), MagicMock()
    engine.decide.return_value = {"answers": {"task_type": {"choice": "planning",
                                                             "answer_confidence": 0.81}},
                                  "routing": {"model": "english"}}
    observer = LayaDecisionShadowObserver(engine, event_sink=sink)
    try:
        assert observer.submit({"prompt": "private user content"}, "planning")
    finally:
        observer.close(wait=True)
    event = sink.call_args.args[0]
    assert event["agreement"] is True
    assert event["confidence"] == 0.81
    assert "private user content" not in repr(event)

def test_shadow_observer_drops_context_without_text():
    engine = MagicMock()
    observer = LayaDecisionShadowObserver(engine)
    try:
        assert observer.submit({"task_type": "planning"}, "planning") is False
        engine.decide.assert_not_called()
    finally:
        observer.close(wait=True)

def test_shadow_observer_drops_samples_when_queue_is_full():
    engine, gate = MagicMock(), threading.Event()
    engine.decide.side_effect = lambda *_args: gate.wait(1)
    observer = LayaDecisionShadowObserver(engine, max_workers=1, max_pending=1)
    try:
        assert observer.submit({"prompt": "first"}, "general")
        assert observer.submit({"prompt": "second"}, "general") is False
    finally:
        gate.set()
        observer.close(wait=True)


def test_laya_adapter_rejects_http_hostname_prefix_spoof():
    with pytest.raises(ValueError, match="loopback"):
        LayaDecisionAdapter("http://127.0.0.1.attacker.invalid:8000")


def test_llm_router_shadow_observation_does_not_change_selected_adapter():
    from app.application.services.llm_router import LLMRouter

    observer = MagicMock()
    adapter = MagicMock()
    adapter.execute.return_value = {"success": True, "response": "done"}
    router = LLMRouter(decision_observer=observer)
    router._resolve_adapter = lambda _name: adapter
    router._is_reliable = lambda _name: True
    router._is_available = lambda _adapter: True

    result = router.execute({"task_type": "planning", "prompt": "plan a migration"})

    assert result["success"] is True
    assert result["routed_to"] == "MagicMock"
    observer.submit.assert_called_once_with(
        {"task_type": "planning", "prompt": "plan a migration"}, "planning"
    )
    adapter.execute.assert_called_once()


def test_llm_router_continues_when_shadow_observer_fails():
    from app.application.services.llm_router import LLMRouter

    observer = MagicMock()
    observer.submit.side_effect = RuntimeError("shadow unavailable")
    adapter = MagicMock()
    adapter.execute.return_value = {"success": True}
    router = LLMRouter(decision_observer=observer)
    router._resolve_adapter = lambda _name: adapter
    router._is_reliable = lambda _name: True
    router._is_available = lambda _adapter: True

    result = router.execute({"task_type": "planning", "prompt": "plan safely"})

    assert result["success"] is True
    adapter.execute.assert_called_once()


def test_shadow_observer_supports_custom_typed_questions():
    sink, engine = MagicMock(), MagicMock()
    engine.decide.return_value = {
        "answers": {"command_type": {"choice": "open_url", "answer_confidence": 0.92}},
        "routing": {"model": "multilingual"},
    }
    observer = LayaDecisionShadowObserver(engine, event_sink=sink)
    question = {
        "type": "choice",
        "instructions": "Qual comando corresponde à solicitação?",
        "criteria": {"open_url": "Abrir URL", "type_text": "Digitar texto"},
    }
    try:
        assert observer.submit_question(
            {"request": "abra example.com"}, "command_type", question, "open_url",
            event_name="laya_shadow_intent",
        )
    finally:
        observer.close(wait=True)
    event = sink.call_args.args[0]
    assert event["event"] == "laya_shadow_intent"
    assert event["predicted_value"] == "open_url"
    assert event["existing_value"] == "open_url"
    assert event["agreement"] is True


def test_intent_processor_shadow_does_not_change_execution():
    from app.domain.services.intent_processor import IntentProcessor
    observer = MagicMock()
    processor = IntentProcessor(decision_observer=observer)
    intent = __import__("app.domain.models", fromlist=["Intent"]).Intent(
        command_type=__import__("app.domain.models", fromlist=["CommandType"]).CommandType.TYPE_TEXT,
        raw_input="digite olá",
    )
    executor = MagicMock()
    executor.execute.return_value = {"message": "Texto digitado"}
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "app.domain.services.intent_processor.nexus"
    ) as nexus_mock:
        nexus_mock.resolve.return_value = executor
        result = processor.execute({"intent": intent})
    assert result == "Texto digitado"
    observer.submit_question.assert_called_once()
    executor.execute.assert_called_once()


def test_task_queue_shadow_observes_without_changing_enqueue():
    from app.application.services.agent_task_queue_service import AgentTaskQueueService
    observer = MagicMock()
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    service = AgentTaskQueueService(engine, decision_observer=observer)
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one.return_value = {
        "task_id": "task-1", "task_type": "planning", "priority": 60, "status": "ready"
    }
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    engine.begin = MagicMock(return_value=transaction)
    result = service.enqueue("task-1", "Plan migration", task_type="planning", priority=60)
    assert result["task_id"] == "task-1"
    observer.submit.assert_called_once()
    assert observer.submit.call_args.args[1] == "planning"
