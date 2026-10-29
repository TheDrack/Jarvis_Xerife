from unittest.mock import Mock

from app.adapters.infrastructure import respan_tracing


def test_tracing_is_skipped_without_api_key(monkeypatch):
    monkeypatch.delenv("RESPAN_API_KEY", raising=False)
    monkeypatch.setattr(respan_tracing, "_initialization_attempted", False)
    monkeypatch.setattr(respan_tracing, "_respan_instance", None)

    assert respan_tracing.initialize_respan_tracing() is None


def test_tracing_initializes_once_when_key_is_configured(monkeypatch):
    fake_instance = Mock()
    monkeypatch.setenv("RESPAN_API_KEY", "test-key-not-a-real-secret")
    monkeypatch.setattr(respan_tracing, "_initialization_attempted", False)
    monkeypatch.setattr(respan_tracing, "_respan_instance", None)
    monkeypatch.setattr(respan_tracing, "_respan_class_for_test", None, raising=False)

    class FakeRespan:
        def __new__(cls):
            return fake_instance

    import sys
    fake_module = type(sys)("respan")
    fake_module.Respan = FakeRespan
    monkeypatch.setitem(sys.modules, "respan", fake_module)

    assert respan_tracing.initialize_respan_tracing() is fake_instance
    assert respan_tracing.initialize_respan_tracing() is fake_instance
    fake_instance.shutdown.assert_not_called()


def test_shutdown_flushes_sdk_and_is_idempotent(monkeypatch):
    fake_instance = Mock()
    monkeypatch.setattr(respan_tracing, "_respan_instance", fake_instance)

    respan_tracing.shutdown_respan_tracing()
    respan_tracing.shutdown_respan_tracing()

    fake_instance.shutdown.assert_called_once_with()
