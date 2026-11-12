from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_windows_bundle_spec_contains_hud_assets_and_embedded_icon():
    spec_path = ROOT / "JarvisDesktop.spec"

    assert spec_path.is_file()
    spec = spec_path.read_text(encoding="utf-8")

    assert "('app/static', 'app/static')" in spec
    assert "('desktop', 'desktop')" in spec
    assert "icon=['desktop/jarvis.ico']" in spec
    assert "console=False" in spec
    assert "coll = COLLECT(" in spec


def test_windows_build_script_validates_the_packaged_executable_and_icon():
    script_path = ROOT / "scripts" / "build_jarvis_desktop.ps1"

    assert script_path.is_file()
    script = script_path.read_text(encoding="utf-8")

    assert "JarvisDesktop.spec" in script
    assert "JarvisDesktop.exe" in script
    assert "_internal\\desktop\\jarvis.ico" in script
    assert "$LASTEXITCODE -ne 0" in script


def test_windows_bundle_includes_the_mcp_sdk_required_by_gods_eye():
    spec = (ROOT / "JarvisDesktop.spec").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements" / "desktop.txt").read_text(encoding="utf-8")

    assert "mcp>=1.30,<2" in requirements
    assert "collect_submodules('mcp.client')" in spec
    assert "collect_submodules('mcp.shared')" in spec
