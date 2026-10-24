"""Tests for the isolated optional ARTEMIS Android adapter."""
from types import SimpleNamespace

from app.adapters.edge.artemis_android_navigation_adapter import ArtemisAndroidNavigationAdapter


def test_rejects_empty_instruction_without_client():
    adapter = ArtemisAndroidNavigationAdapter(server_url="http://localhost:8000")
    result = adapter.run_task(" ", "phone-01")
    assert result["success"] is False
    assert result["status"] == "invalid_instruction"


def test_requires_explicit_device_id():
    adapter = ArtemisAndroidNavigationAdapter(server_url="http://localhost:8000")
    result = adapter.run_task("Open settings", "")
    assert result["success"] is False
    assert result["status"] == "configuration_error"


def test_rejects_unknown_profile():
    adapter = ArtemisAndroidNavigationAdapter(server_url="http://localhost:8000")
    result = adapter.run_task("Open settings", "phone-01", profile="turbo")
    assert result["status"] == "invalid_profile"


def test_runs_task_on_explicit_device_and_returns_trace():
    calls = []

    class FakeClient:
        def run(self, instruction, profile):
            calls.append((instruction, profile))
            return SimpleNamespace(
                succeeded=True, status="completed", trace_id="trace-123",
                error=None, model_dump=lambda: {"succeeded": True}
            )

    def factory(server_url, device_serial, default_profile):
        assert server_url == "http://localhost:8000"
        assert device_serial == "phone-01"
        assert default_profile == "pro"
        return FakeClient()

    adapter = ArtemisAndroidNavigationAdapter(
        server_url="http://localhost:8000", client_factory=factory
    )
    result = adapter.run_task("Open Settings and verify it", "phone-01", "pro")
    assert result["success"] is True
    assert result["trace_id"] == "trace-123"
    assert calls == [("Open Settings and verify it", "pro")]


def test_missing_sdk_is_reported_without_crashing(monkeypatch):
    adapter = ArtemisAndroidNavigationAdapter(server_url="")
    result = adapter.run_task("Open Settings", "phone-01")
    assert result["success"] is False
    assert result["status"] == "configuration_error"
