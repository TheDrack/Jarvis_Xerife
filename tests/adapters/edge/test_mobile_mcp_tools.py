import asyncio
import base64
import json

from mcp.server.fastmcp import FastMCP

from app.adapters.edge.android_navigation_adapter import AndroidNavigationAdapter
from app.adapters.edge.mobile_mcp_tools import MOBILE_CAPABILITIES, register_mobile_tools
from tests.adapters.edge.test_android_navigation_adapter import FakeConn, PNG, XML


def build(conn=None):
    conn = conn or FakeConn()
    nav = AndroidNavigationAdapter(lambda serial: conn, sleep=lambda s: None)
    mcp = FastMCP("test")
    register_mobile_tools(mcp, nav)
    return mcp, conn


def call(mcp, name, args):
    return asyncio.run(mcp.call_tool(name, args))


def test_all_mobile_tools_are_registered():
    mcp, _ = build()
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {
        "mobile_observe", "mobile_find_element", "mobile_run_recipe",
        "mobile_tap", "mobile_type", "mobile_press_key", "mobile_launch_app",
    } <= names


def test_observe_returns_text_and_png_image_block():
    mcp, _ = build()
    blocks = call(mcp, "mobile_observe", {"device_id": "abc"})
    kinds = [getattr(b, "type", None) for b in blocks]
    assert "text" in kinds and "image" in kinds
    image = next(b for b in blocks if getattr(b, "type", None) == "image")
    assert base64.b64decode(image.data).startswith(b"\x89PNG")


def test_tap_by_resource_id_taps_center():
    mcp, conn = build()
    call(mcp, "mobile_tap", {"device_id": "abc", "resource_id": "com.app:id/send", "user_confirmed": True})
    assert ("tap", 200, 230) in conn.actions


def test_sensitive_tap_requires_confirmation_and_does_not_tap():
    mcp, conn = build()
    blocks = call(mcp, "mobile_tap", {"device_id": "abc", "text": "Enviar"})
    meta = json.loads(blocks[0].text)
    assert meta["status"] == "confirmation_required"
    assert conn.actions == []


def test_sensitive_tap_runs_with_confirmation():
    mcp, conn = build()
    blocks = call(mcp, "mobile_tap", {"device_id": "abc", "text": "Enviar", "user_confirmed": True})
    assert ("tap", 200, 230) in conn.actions
    assert json.loads(blocks[0].text)["status"] == "completed"


def test_press_key_rejects_disallowed_keycode():
    mcp, conn = build()
    blocks = call(mcp, "mobile_press_key", {"device_id": "abc", "keycode": 26})
    assert json.loads(blocks[0].text)["status"] == "invalid_recipe"
    assert conn.actions == []


def test_launch_app_invokes_connection():
    mcp, conn = build()
    call(mcp, "mobile_launch_app", {"device_id": "abc", "package": "com.android.settings"})
    assert ("launch", "com.android.settings") in conn.actions


def test_capability_names_match_service_contract():
    assert MOBILE_CAPABILITIES == ("mobile.observe", "mobile.tap", "mobile.type", "mobile.key", "mobile.launch_app")
