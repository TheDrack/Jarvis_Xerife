import pytest

from app.adapters.connection.adb_connection import (
    AdbConnection,
    AdbError,
    CommandResult,
    escape_for_input_text,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


class Recorder:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __call__(self, argv, timeout):
        self.calls.append(list(argv))
        key = " ".join(argv[3:])
        for prefix, result in self.responses.items():
            if key.startswith(prefix):
                return result
        return CommandResult(0, b"", b"")


def ok(out=b""):
    return CommandResult(0, out, b"")


def test_rejects_invalid_serial():
    with pytest.raises(AdbError):
        AdbConnection("bad serial; rm -rf /")


def test_tap_builds_argv_with_serial_and_checks_coordinates():
    rec = Recorder()
    conn = AdbConnection("emulator-5554", runner=rec)
    conn.tap(10, 20)
    assert rec.calls == [["adb", "-s", "emulator-5554", "shell", "input", "tap", "10", "20"]]
    with pytest.raises(AdbError):
        conn.tap(-1, 0)


def test_is_connected_requires_device_state():
    assert AdbConnection("abc", runner=Recorder({"get-state": ok(b"device\n")})).is_connected()
    assert not AdbConnection("abc", runner=Recorder({"get-state": ok(b"unauthorized\n")})).is_connected()


def test_is_connected_false_when_adb_missing():
    def boom(argv, timeout):
        raise AdbError("adb não encontrado")
    assert not AdbConnection("abc", runner=boom).is_connected()


def test_screencap_requires_png_signature():
    conn = AdbConnection("abc", runner=Recorder({"exec-out screencap": ok(PNG)}))
    assert conn.screencap_png().startswith(b"\x89PNG")
    bad = AdbConnection("abc", runner=Recorder({"exec-out screencap": ok(b"nope")}))
    with pytest.raises(AdbError):
        bad.screencap_png()


def test_dump_hierarchy_strips_uiautomator_banner():
    raw = b'UI hierchary dumped to: /dev/tty\n<?xml version="1.0"?><hierarchy rotation="0"></hierarchy>'
    conn = AdbConnection("abc", runner=Recorder({"shell uiautomator": ok(raw)}))
    assert conn.dump_hierarchy().startswith("<?xml")


def test_launch_app_validates_package_name():
    rec = Recorder()
    conn = AdbConnection("abc", runner=rec)
    conn.launch_app("com.whatsapp")
    assert rec.calls[0][3:6] == ["shell", "monkey", "-p"]
    with pytest.raises(AdbError):
        conn.launch_app("com.x; reboot")


def test_key_event_only_allowed_keycodes():
    rec = Recorder()
    conn = AdbConnection("abc", runner=rec)
    conn.key_event(4)
    with pytest.raises(AdbError):
        conn.key_event(26)  # POWER não está na lista


def test_nonzero_exit_raises_with_stderr():
    conn = AdbConnection("abc", runner=Recorder({"shell input": CommandResult(1, b"", b"device offline")}))
    with pytest.raises(AdbError, match="device offline"):
        conn.tap(1, 1)


def test_escape_text_replaces_spaces_and_escapes_meta():
    assert escape_for_input_text("oi tudo") == "oi%studo"
    assert escape_for_input_text("a;b") == "a\\;b"
    with pytest.raises(AdbError):
        escape_for_input_text("olá")  # não-ASCII
    with pytest.raises(AdbError):
        escape_for_input_text("")
