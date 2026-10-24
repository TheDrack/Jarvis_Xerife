import base64

from app.adapters.connection.adb_connection import AdbError
from app.adapters.edge.android_navigation_adapter import (
    AndroidNavigationAdapter,
    parse_bounds,
    parse_elements,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
XML = """<?xml version='1.0'?>
<hierarchy>
  <node class="android.widget.Button" text="Enviar" resource-id="com.app:id/send"
        clickable="true" bounds="[100,200][300,260]" content-desc="" />
  <node class="android.widget.TextView" text="Oi" resource-id="com.app:id/msg"
        clickable="false" bounds="[0,0][50,50]" content-desc="" />
  <node class="android.widget.Button" text="Vazio" resource-id="" bounds="[5,5][5,9]" />
</hierarchy>"""


class FakeConn:
    def __init__(self, connected=True, xml=XML, fail=None):
        self.connected = connected
        self.xml = xml
        self.fail = fail
        self.actions = []

    def is_connected(self):
        return self.connected

    def screencap_png(self):
        return PNG

    def dump_hierarchy(self):
        return self.xml

    def tap(self, x, y):
        self.actions.append(("tap", x, y))

    def type_text(self, text):
        self.actions.append(("type", text))

    def key_event(self, code):
        self.actions.append(("key", code))

    def launch_app(self, pkg):
        self.actions.append(("launch", pkg))

    def force_stop(self, pkg):
        self.actions.append(("stop", pkg))


def adapter(conn, sleep=lambda s: None):
    return AndroidNavigationAdapter(lambda serial: conn, sleep=sleep)


def test_parse_bounds_rejects_degenerate_boxes():
    assert parse_bounds("[1,2][3,4]") == (1, 2, 3, 4)
    assert parse_bounds("[5,5][5,9]") is None
    assert parse_bounds("garbage") is None


def test_parse_elements_skips_invalid_bounds_and_computes_center():
    els = parse_elements(XML)
    assert [e["resource_id"] for e in els] == ["com.app:id/send", "com.app:id/msg"]
    assert els[0]["center"] == (200, 230)
    assert els[0]["clickable"] is True


def test_observe_returns_png_and_elements():
    out = adapter(FakeConn()).observe("abc")
    assert out["status"] == "observed"
    assert base64.b64decode(out["screenshot_png_b64"]).startswith(b"\x89PNG")
    assert len(out["elements"]) == 2


def test_observe_unavailable_when_not_authorized():
    assert adapter(FakeConn(connected=False)).observe("abc")["status"] == "unavailable"


def test_observe_handles_adb_error():
    class Broken(FakeConn):
        def screencap_png(self):
            raise AdbError("sem permissão")
    assert adapter(Broken()).observe("abc") == {"status": "unavailable", "message": "sem permissão", }


def test_find_statuses():
    a = adapter(FakeConn())
    assert a.find("abc", resource_id="com.app:id/send")["status"] == "found"
    assert a.find("abc", resource_id="com.app:id/nope")["status"] == "not_found"
    dup = XML.replace('resource-id="com.app:id/msg"', 'resource-id="com.app:id/send"')
    assert adapter(FakeConn(xml=dup)).find("abc", resource_id="com.app:id/send")["status"] == "ambiguous"


def test_recipe_taps_by_resource_id_and_verifies_text():
    conn = FakeConn()
    steps = [{
        "target": {"resource_id": "com.app:id/send"},
        "action": "tap",
        "verify": {"text": "Oi"},
    }]
    out = adapter(conn).run_recipe("abc", steps)
    assert out == {"status": "completed", "device_id": "abc", "completed_steps": 1}
    assert conn.actions == [("tap", 200, 230)]


def test_recipe_postcondition_failure_stops_and_reports_step():
    conn = FakeConn()
    steps = [
        {"action": "launch", "value": "com.app"},
        {"target": {"text": "Enviar"}, "action": "tap", "verify": {"text": "Tela inexistente"}},
        {"action": "key", "value": 4},
    ]
    out = adapter(conn).run_recipe("abc", steps)
    assert out["status"] == "postcondition_failed"
    assert out["step"] == 1 and out["completed_steps"] == 1
    assert ("key", 4) not in conn.actions


def test_recipe_missing_target_returns_not_found_without_tapping():
    conn = FakeConn()
    out = adapter(conn).run_recipe("abc", [{"target": {"text": "Não existe"}, "action": "tap"}])
    assert out["status"] == "not_found"
    assert conn.actions == []


def test_recipe_validation_rejects_bad_steps():
    a = adapter(FakeConn())
    assert a.run_recipe("abc", [])["status"] == "invalid_recipe"
    assert a.run_recipe("abc", [{"action": "rm"}])["status"] == "invalid_recipe"
    assert a.run_recipe("abc", [{"action": "tap"}])["status"] == "invalid_recipe"
    assert a.run_recipe("abc", [{"action": "launch"}])["status"] == "invalid_recipe"
    assert a.run_recipe("abc", [{"action": "type", "value": "x", "verify": {}}])["status"] == "invalid_recipe"


def test_recipe_too_many_steps():
    steps = [{"action": "key", "value": 4}] * 21
    assert adapter(FakeConn()).run_recipe("abc", steps)["status"] == "invalid_recipe"


def test_execute_dispatches_observe_and_unknown():
    a = adapter(FakeConn())
    assert a.execute({"action": "observe", "device_id": "abc"})["status"] == "observed"
    assert a.execute({"action": "wat"})["status"] == "invalid_recipe"
