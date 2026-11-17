from __future__ import annotations

from pathlib import Path

from scripts.autodoc import generate_jarvis_graph


def test_generated_map_excludes_archives_and_runtime_data(tmp_path: Path) -> None:
    (tmp_path / ".backups" / "legacy").mkdir(parents=True)
    (tmp_path / ".backups" / "legacy" / "obsolete.py").write_text(
        "class Obsolete: pass\n", encoding="utf-8"
    )
    (tmp_path / "backups" / "old").mkdir(parents=True)
    (tmp_path / "backups" / "old" / "archived.py").write_text(
        "class Archived: pass\n", encoding="utf-8"
    )
    (tmp_path / "data" / "runtime").mkdir(parents=True)
    (tmp_path / "data" / "runtime" / "state.py").write_text(
        "class RuntimeState: pass\n", encoding="utf-8"
    )
    (tmp_path / "app" / "domain").mkdir(parents=True)
    (tmp_path / "app" / "domain" / "current.py").write_text(
        "class CurrentDomain: pass\n", encoding="utf-8"
    )
    (tmp_path / "mobile" / "android").mkdir(parents=True)

    generated = generate_jarvis_graph(str(tmp_path))

    assert "app_domain" in generated
    assert "mobile_android" in generated
    assert "obsolete.py" not in generated
    assert "archived.py" not in generated
    assert "RuntimeState" not in generated
    assert ".backups" not in generated
    assert "backups" not in generated
    assert "data_runtime" not in generated
