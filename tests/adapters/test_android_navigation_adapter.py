"""Unit tests for the additive Android ADB adapter; no live device required."""
import base64
import subprocess

from app.adapters.edge.android_navigation_adapter import AndroidNavigationAdapter


def completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def test_missing_device_is_reported_without_invoking_adb(monkeypatch):
    monkeypatch.delenv("JARVIS_ANDROID_DEVICE", raising=False)
    adapter = AndroidNavigationAdapter(device_address="")
    assert adapter.tap(10, 20)["status"] == "device_not_configured"


def test_tap_uses_explicit_device_and_adb(monkeypatch):
    calls = []
    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return completed(args)
    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = AndroidNavigationAdapter(device_address="100.64.0.8:37123", adb_path="/tools/adb")
    result = adapter.tap(12, 34)
    assert result["success"] is True
    assert calls[0][0] == ["/tools/adb", "-s", "100.64.0.8:37123", "shell", "input", "tap", "12", "34"]


def test_invalid_coordinates_do_not_call_adb(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("ADB must not run for invalid coordinates")
    monkeypatch.setattr(subprocess, "run", fail_if_called)
    result = AndroidNavigationAdapter(device_address="phone-1").tap(-1, 2)
    assert result["status"] == "invalid_coordinates"


def test_observe_screen_returns_base64_png(monkeypatch):
    png = b"fake-png-bytes"
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: completed(args, stdout=png))
    result = AndroidNavigationAdapter(device_address="phone-1").observe_screen()
    assert result["success"] is True
    assert result["image_format"] == "png"
    assert result["image_base64"] == base64.b64encode(png).decode("ascii")


def test_observe_screen_handles_transport_error(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=1)
    monkeypatch.setattr(subprocess, "run", fail)
    result = AndroidNavigationAdapter(device_address="phone-1").observe_screen()
    assert result["success"] is False
    assert result["status"] == "transport_error"


def test_key_allowlist_and_text_length(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: (calls.append(args) or completed(args)))
    adapter = AndroidNavigationAdapter(device_address="phone-1")
    assert adapter.press_key("POWER")["status"] == "unsupported_key"
    assert adapter.type_text("x" * 2001)["status"] == "input_too_long"
    assert calls == []



def test_type_text_escapes_shell_metacharacters(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: (calls.append(args) or completed(args)))
    adapter = AndroidNavigationAdapter(device_address="phone-1")
    result = adapter.type_text("hello world;$(id)%")
    assert result["success"] is True
    sent = calls[0][-1]
    assert "%s" in sent
    assert "\\;" in sent
    assert "\\$" in sent
    assert "\\(" in sent
    assert "%25" in sent
