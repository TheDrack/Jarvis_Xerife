import os
import ast
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(".").resolve()

FROZEN_ROOT = REPO_ROOT / ".frozen"
FROZEN_CAPS = FROZEN_ROOT / "caps"
FROZEN_OTHERS = FROZEN_ROOT / "others"
FROZEN_INDEX = FROZEN_ROOT / "frozen_index.json"

IMMUTABLE_PATHS = [
    "app/core",
    "app/runtime",
    "app/bootstrap",
    "tests",
    "docs",
    "scripts",
    "dags",
    "__init__.py",
    "setup.py",
    "build_config.py",
]

CAPABILITY_MARKERS = [
    "/capabilities/",
    "/gears/",
]

# ---------------------------------------------------------------------

def is_immutable(rel_path: str) -> bool:
    return any(rel_path.startswith(p) or rel_path == p for p in IMMUTABLE_PATHS)

def is_capability(rel_path: str) -> bool:
    return (
        any(m in rel_path for m in CAPABILITY_MARKERS)
        or Path(rel_path).name.startswith("cap_")
    )

def load_index():
    if not FROZEN_INDEX.exists():
        return {}
    return json.loads(FROZEN_INDEX.read_text())

def save_index(index):
    FROZEN_ROOT.mkdir(exist_ok=True)
    FROZEN_CAPS.mkdir(exist_ok=True)
    FROZEN_OTHERS.mkdir(exist_ok=True)
    FROZEN_INDEX.write_text(json.dumps(index, indent=2))

# ---------------------------------------------------------------------

def discover_used_modules():
    used = set()

    for py in REPO_ROOT.rglob("*.py"):
        rel = str(py.relative_to(REPO_ROOT))

        if is_immutable(rel):
            continue

        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    used.add(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                used.add(node.module.split(".")[0])

    return used

# ---------------------------------------------------------------------

def freeze_file(rel_path: str, index: dict):
    src = REPO_ROOT / rel_path
    name = src.name

    if is_capability(rel_path):
        dst = FROZEN_CAPS / name
        ftype = "capability"
    else:
        dst = FROZEN_OTHERS / name
        ftype = "other"

    if dst.exists():
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

    index[name] = {
        "original_path": rel_path,
        "type": ftype,
    }

    print(f"🧊 FROZEN: {rel_path}")

# ---------------------------------------------------------------------

def unfreeze_used(index: dict, used_modules: set):
    restored = []

    for name, meta in list(index.items()):
        original = REPO_ROOT / meta["original_path"]
        frozen_path = (
            FROZEN_CAPS / name
            if meta["type"] == "capability"
            else FROZEN_OTHERS / name
        )

        if not frozen_path.exists():
            continue

        module_name = Path(name).stem
        if module_name in used_modules:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(frozen_path), str(original))
            restored.append(name)
            del index[name]
            print(f"🔥 UNFROZEN: {name}")

    return restored

# ---------------------------------------------------------------------

def main():
    print("=" * 80)
    print("Repo Lifecycle Governance — SAFE MODE")
    print("=" * 80)

    index = load_index()
    used = discover_used_modules()

    print(f"[DISCOVERY] TOTAL used: {len(used)}")

    unfreeze_used(index, used)

    for py in REPO_ROOT.rglob("*.py"):
        rel = str(py.relative_to(REPO_ROOT))

        # 🚫 REGRA ABSOLUTA
        if is_immutable(rel):
            continue

        if not is_capability(rel):
            continue

        name = py.stem
        if name not in used:
            freeze_file(rel, index)

    save_index(index)

    print("-" * 80)
    print("Governança concluída sem falhas")
    print("-" * 80)

# ---------------------------------------------------------------------

if __name__ == "__main__":
    main()