import base64
import io

from PIL import Image

from app.adapters.edge.visual_navigation_adapter import VisualNavigationAdapter


class FakePyAutoGUI:
    FAILSAFE = False

    def __init__(self, image):
        self.image = image
        self.clicks = []

    def screenshot(self):
        return self.image.copy()

    def locateAll(self, *args, **kwargs):
        return iter([])

    def center(self, box):
        raise AssertionError("A missing template must never be clicked.")

    def click(self, *args, **kwargs):
        self.clicks.append((args, kwargs))


def test_missing_template_stops_before_click_and_returns_screen(tmp_path):
    gui = FakePyAutoGUI(Image.new("RGB", (160, 90), (30, 80, 150)))
    adapter = VisualNavigationAdapter(
        pyautogui_module=gui,
        template_dir=tmp_path / "templates",
        screenshot_dir=tmp_path / "captures",
    )

    result = adapter.run_recipe([
        {"template_id": "save_button", "verify_template_id": "saved_state"}
    ])

    assert result["success"] is False
    assert result["status"] == "needs_template"
    assert result["requested_template_id"] == "save_button"
    assert "screenshot_data_url" in result
    assert result["screenshot_path"]
    assert gui.clicks == []


def test_save_template_creates_png_and_catalog(tmp_path):
    image = Image.new("RGB", (40, 24), (220, 30, 90))
    pixels = image.load()
    for x in range(20):
        for y in range(24):
            pixels[x, y] = (20, 200, 40)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    adapter = VisualNavigationAdapter(
        template_dir=tmp_path / "templates",
        screenshot_dir=tmp_path / "captures",
    )

    result = adapter.save_template("save_button", encoded, "Salvar")

    assert result["success"] is True
    assert (tmp_path / "templates" / "save_button.png").is_file()
    assert (tmp_path / "templates" / "catalog.json").is_file()


def test_recipe_requires_postcondition_before_any_action(tmp_path):
    gui = FakePyAutoGUI(Image.new("RGB", (160, 90), (10, 20, 30)))
    adapter = VisualNavigationAdapter(
        pyautogui_module=gui,
        template_dir=tmp_path / "templates",
        screenshot_dir=tmp_path / "captures",
    )

    result = adapter.run_recipe([{"template_id": "submit"}])

    assert result["success"] is False
    assert result["status"] == "invalid_recipe"
    assert gui.clicks == []



def test_recipe_prefers_semantic_invocation_and_verifies_without_template(tmp_path, monkeypatch):
    gui = FakePyAutoGUI(Image.new("RGB", (160, 90), (30, 80, 150)))
    adapter = VisualNavigationAdapter(
        pyautogui_module=gui,
        template_dir=tmp_path / "templates",
        screenshot_dir=tmp_path / "captures",
    )
    calls = []

    def semantic(target_name, window_title_contains="", control_type="", expected_name_after="", timeout_seconds=2.0):
        calls.append((target_name, expected_name_after))
        return {
            "success": True,
            "status": "postcondition_verified",
            "input_mode": "uia_invoke_non_physical",
            "target_name": target_name,
            "expected_name_after": expected_name_after,
        }

    monkeypatch.setattr(adapter, "click_accessibility", semantic)
    result = adapter.run_recipe([{
        "target_name": "Salvar",
        "expected_name_after": "Salvo",
    }])

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["completed_steps"][0]["strategy"] == "accessibility_invoke"
    assert calls == [("Salvar", "Salvo")]
    assert gui.clicks == []


def test_template_recipe_does_not_use_physical_mouse_without_explicit_opt_in(tmp_path, monkeypatch):
    gui = FakePyAutoGUI(Image.new("RGB", (160, 90), (30, 80, 150)))
    adapter = VisualNavigationAdapter(
        pyautogui_module=gui,
        template_dir=tmp_path / "templates",
        screenshot_dir=tmp_path / "captures",
    )

    class Box:
        x, y = 40, 20

    monkeypatch.setattr(adapter, "_find_unique", lambda image, template_id, confidence: ("found", object()))
    monkeypatch.setattr(adapter._gui(), "center", lambda match: Box())
    monkeypatch.setattr(adapter, "_invoke_accessible_at", lambda x, y: {
        "success": False, "status": "no_accessible_control_at_point"
    })

    result = adapter.run_recipe([{
        "template_id": "save_button",
        "verify_template_id": "saved_state",
    }])

    assert result["success"] is False
    assert result["status"] == "background_input_unavailable"
    assert gui.clicks == []


def test_compact_accessibility_snapshot_is_bounded_and_omits_geometry():
    from app.adapters.edge.jarvis_desktop_cli import _compact_accessibility_snapshot

    snapshot = _compact_accessibility_snapshot([{"title": "Settings", "elements": [
        {"name": "Save", "control_type": "Button", "automation_id": "save", "enabled": True, "rectangle": [1, 2, 3, 4]},
        {"name": "", "control_type": "Pane", "automation_id": "", "enabled": True},
        {"name": "Cancel", "control_type": "Button", "automation_id": "", "enabled": False, "rectangle": [5, 6, 7, 8]},
    ]}])
    assert snapshot["status"] == "semantic_ui_snapshot"
    assert snapshot["element_count"] == 2
    assert snapshot["windows"][0]["elements"][0]["name"] == "Save"
    assert "rectangle" not in snapshot["windows"][0]["elements"][0]
    assert snapshot["windows"][0]["elements"][1]["enabled"] is False
    assert snapshot["id_scope"] == "display_only_this_snapshot"


def test_compact_accessibility_snapshot_caps_element_count():
    from app.adapters.edge.jarvis_desktop_cli import _compact_accessibility_snapshot

    windows = [{"title": "App", "elements": [
        {"name": f"Button {i}", "control_type": "Button", "enabled": True} for i in range(20)
    ]}]
    snapshot = _compact_accessibility_snapshot(windows, max_elements=3)
    assert snapshot["element_count"] == 3
    assert snapshot["truncated"] is True
