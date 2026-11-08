"""Tests for the optional Laya decision adapter and shadow observer."""
from __future__ import annotations
import json
import threading
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
