from pathlib import Path

from app.adapters import jarvis_return_activity as watcher


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def read(self):
        return b"{}"


class FakeConnection:
    def __init__(self, host, port, timeout, context):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.request_args = None
        self.closed = False
        self.status = 200

    def request(self, method, path, body, headers):
        self.request_args = (method, path, body, headers)

    def getresponse(self):
        return FakeResponse(self.status)

    def close(self):
        self.closed = True


def test_return_activity_sends_fixed_event_using_dedicated_key(monkeypatch):
    connections = []

    def create_connection(*args, **kwargs):
        connection = FakeConnection(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setenv("JARVIS_API_BASE_URL", "https://jarvis.example.test/")
    monkeypatch.setenv("JARVIS_RETURN_ACTIVITY_KEY", "test-machine-key")
    monkeypatch.setattr(watcher.http.client, "HTTPSConnection", create_connection)

    assert watcher._send_welcome_to_mobile() is True
    assert len(connections) == 1
    connection = connections[0]
    assert connection.host == "jarvis.example.test"
    assert connection.request_args == (
        "POST",
        "/v1/mobile/push/return-activity",
        b"{}",
        {
            "X-Jarvis-Return-Activity-Key": "test-machine-key",
            "Content-Type": "application/json",
        },
    )
    assert connection.timeout == 10
    assert connection.closed is True


def test_return_activity_does_not_attempt_network_without_key(monkeypatch):
    monkeypatch.delenv("JARVIS_RETURN_ACTIVITY_KEY", raising=False)
    monkeypatch.setattr(watcher, "LOG_DIR", Path("Z:/missing/jarvis/logs"))
    calls = []
    monkeypatch.setattr(
        watcher.http.client,
        "HTTPSConnection",
        lambda *args, **kwargs: calls.append(args),
    )

    assert watcher._send_welcome_to_mobile() is False
    assert calls == []


def test_return_activity_reports_server_rejection_without_leaking_key(monkeypatch):
    connections = []

    def create_connection(*args, **kwargs):
        connection = FakeConnection(*args, **kwargs)
        connection.status = 503
        connections.append(connection)
        return connection

    monkeypatch.setenv("JARVIS_RETURN_ACTIVITY_KEY", "test-machine-key")
    monkeypatch.setattr(watcher.http.client, "HTTPSConnection", create_connection)

    assert watcher._send_welcome_to_mobile() is False
    assert connections[0].closed is True
