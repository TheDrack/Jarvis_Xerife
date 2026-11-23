from __future__ import annotations

from scripts import manage_agent_worker_credentials as command


def test_set_provider_updates_trusted_agent_without_rotating_credential(monkeypatch, capsys):
    calls = []

    class FakeEngine:
        def dispose(self):
            calls.append(("dispose",))

    class FakeStore:
        def __init__(self, engine):
            assert isinstance(engine, FakeEngine)

        def set_model_provider(self, agent_id, model_provider):
            calls.append(("set_model_provider", agent_id, model_provider))

    monkeypatch.setattr(command, "_database_url", lambda: "postgresql://example")
    monkeypatch.setattr(command, "create_engine", lambda *_args, **_kwargs: FakeEngine())
    monkeypatch.setattr(command, "AgentWorkerCredentialStore", FakeStore)

    result = command.main([
        "set-provider", "--agent-id", "jarvis-termux-mini-1",
        "--model-provider", "android_app:claude",
    ])

    assert result == 0
    assert calls[0] == ("set_model_provider", "jarvis-termux-mini-1", "android_app:claude")
    assert calls[1] == ("dispose",)
    assert "without rotating" in capsys.readouterr().out.lower()
