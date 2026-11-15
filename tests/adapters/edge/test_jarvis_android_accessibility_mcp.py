from __future__ import annotations

import json

import pytest

from app.adapters.edge import android_accessibility_client as android_mcp


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "back"},
        {"action": "home"},
        {"action": "recents"},
        {"action": "tap", "x": 10, "y": 20},
        {"action": "swipe", "x1": 1, "y1": 2, "x2": 3, "y2": 4, "duration_ms": 350},
        {"action": "click_text", "text": "Continuar"},
        {"action": "click_view_id", "view_id": "com.example:id/continue"},
        {"action": "set_text", "view_id": "com.example:id/input", "text": "Jarvis"},
    ],
)
def test_accessibility_action_accepts_supported_contract(payload):
    assert android_mcp.validate_accessibility_action(payload) == payload


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "launch_app"},
        {"action": "tap", "x": -1, "y": 2},
        {"action": "tap", "x": True, "y": 2},
        {"action": "swipe", "x1": 0, "y1": 0, "x2": 1, "y2": 1, "duration_ms": 10},
        {"action": "click_text", "text": ""},
        {"action": "set_text", "view_id": "x", "text": "x", "password": True},
        {"action": "back", "arbitrary": "field"},
    ],
)
def test_accessibility_action_rejects_invalid_or_unbounded_payloads(payload):
    with pytest.raises(ValueError):
        android_mcp._validate_accessibility_action(payload)


def testaccessibility_token_must_be_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("JARVIS_ANDROID_ACCESSIBILITY_TOKEN", raising=False)
    monkeypatch.setattr(android_mcp, "ACCESSIBILITY_TOKEN_FILE", tmp_path / "missing")
    with pytest.raises(RuntimeError, match="pairing token"):
        android_mcp._accessibility_token()


def testaccessibility_request_uses_loopback_and_bearer_token(monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("a" * 48, encoding="utf-8")
    monkeypatch.delenv("JARVIS_ANDROID_ACCESSIBILITY_TOKEN", raising=False)
    monkeypatch.setattr(android_mcp, "_ACCESSIBILITY_TOKEN_FILE", token_file)

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b'{"status":"ready"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(android_mcp.urllib.request, "urlopen", fake_urlopen)
    assert android_mcp._accessibility_request("/healthz") == {"status": "ready"}
    assert captured == {
        "url": "http://127.0.0.1:18766/healthz",
        "authorization": "Bearer " + "a" * 48,
        "timeout": android_mcp.ACCESSIBILITY_TIMEOUT,
    }


def test_accessibility_action_sends_only_validated_json(monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("b" * 48, encoding="utf-8")
    monkeypatch.delenv("JARVIS_ANDROID_ACCESSIBILITY_TOKEN", raising=False)
    monkeypatch.setattr(android_mcp, "_ACCESSIBILITY_TOKEN_FILE", token_file)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b'{"success":true,"action":"back"}'

    def fake_urlopen(request, timeout):
        captured["method"] = request.method
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(android_mcp.urllib.request, "urlopen", fake_urlopen)
    payload = android_mcp.validate_accessibility_action({"action": "back"})
    assert android_mcp.accessibility_request("/v1/action", payload)["success"] is True
    assert captured == {"method": "POST", "body": {"action": "back"}}


def test_accessibility_endpoint_rejects_non_loopback_hosts(monkeypatch):
    monkeypatch.setattr(android_mcp, "ACCESSIBILITY_URL", "http://192.168.1.10:18766")
    with pytest.raises(RuntimeError, match="loopback"):
        android_mcp._accessibility_endpoint()


def test_accessibility_endpoint_rejects_unexpected_ports(monkeypatch):
    monkeypatch.setattr(android_mcp, "_ACCESSIBILITY_URL", "http://127.0.0.1:9999")
    with pytest.raises(RuntimeError, match="port 18766"):
        android_mcp._accessibility_endpoint()


def test_parameters_cannot_override_the_selected_action():
    with pytest.raises(ValueError, match="cannot override"):
        android_mcp.build_accessibility_action("back", {"action": "home"})


def test_action_builder_validates_parameters_before_transport():
    assert android_mcp.build_accessibility_action("tap", {"x": 10, "y": 20}) == {
        "action": "tap", "x": 10, "y": 20
    }


def test_accessibility_endpoint_requires_explicit_port(monkeypatch):
    monkeypatch.setattr(android_mcp, "ACCESSIBILITY_URL", "http://127.0.0.1")
    with pytest.raises(RuntimeError, match="port 18766"):
        android_mcp.accessibility_endpoint()


@pytest.mark.parametrize("url", ["http://localhost:18766", "http://[::1]:18766"])
def test_accessibility_endpoint_matches_ipv4_listener_only(monkeypatch, url):
    monkeypatch.setattr(android_mcp, "ACCESSIBILITY_URL", url)
    with pytest.raises(RuntimeError, match="loopback"):
        android_mcp.accessibility_endpoint()
