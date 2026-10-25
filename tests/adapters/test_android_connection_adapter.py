import subprocess
from app.adapters.edge import android_connection_adapter as connection


def completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def test_endpoint_accepts_tailscale_and_private_lan():
    assert connection._validate_endpoint("100.95.90.5:36433") == "100.95.90.5:36433"
    assert connection._validate_endpoint("192.168.1.9:5555") == "192.168.1.9:5555"


def test_endpoint_rejects_public_ip():
    try:
        connection._validate_endpoint("8.8.8.8:5555")
    except ValueError as exc:
        assert "Tailscale" in str(exc)
    else:
        raise AssertionError("Public IP must be rejected")


def test_pair_connect_saves_only_connect_endpoint(monkeypatch, tmp_path):
    config = tmp_path / "android-device.json"
    monkeypatch.setattr(connection, "_config_path", lambda: config)
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "pair":
            return completed(args, stdout="Successfully paired to 100.95.90.5:36433")
        return completed(args, stdout="connected to 100.95.90.5:41713")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = connection.pair_and_connect(
        "100.95.90.5:36433", "705576", "100.95.90.5:41713", adb_path="adb-test"
    )
    assert result["success"] is True
    assert calls[0][0] == ["adb-test", "pair", "100.95.90.5:36433", "705576"]
    assert calls[1][0] == ["adb-test", "connect", "100.95.90.5:41713"]
    assert config.read_text(encoding="utf-8").find("705576") == -1
    assert connection.selected_device() == "100.95.90.5:41713"


def test_pair_failure_never_attempts_connect(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: (
        calls.append(args) or completed(args, returncode=1, stderr="failed")
    ))
    result = connection.pair_and_connect("100.95.90.5:36433", "705576", "100.95.90.5:41713")
    assert result["status"] == "pair_failed"
    assert len(calls) == 1


def test_bad_pairing_code_rejected_without_adb(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not run")))
    result = connection.pair_and_connect("100.95.90.5:36433", "bad", "100.95.90.5:41713")
    assert result["status"] == "invalid_pairing_code"
