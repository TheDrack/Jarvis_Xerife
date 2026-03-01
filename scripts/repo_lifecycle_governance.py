import ast
import json
import shutil
from pathlib import Path

ROOT = Path(".").resolve()
FROZEN_ROOT = ROOT / "frozen"
CAPS_FROZEN = FROZEN_ROOT / "caps"
MODULES_FROZEN = FROZEN_ROOT / "modules"
INDEX_FILE = FROZEN_ROOT / "frozen_index.json"

PROTECTED_PATHS = [
    "app/core",
    "app/runtime",
    "app/bootstrap",
    "tests",
    "scripts"
]

CAP_IDENTIFIER = "cap_"

# ------------------ UTILS ------------------

def is_protected(path: Path) -> bool:
    return any(str(path).startswith(p) for p in PROTECTED_PATHS)

def load_index():
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text())
    return {}

def save_index(index):
    FROZEN_ROOT.mkdir(exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, indent=2))

# ------------------ DISCOVERY ------------------

def discover_used_files():
    used = set()

    for py in ROOT.rglob("*.py"):
        if "frozen" in py.parts:
            continue

        try:
            tree = ast.parse(py.read_text())
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = (
                    node.module.split(".")[0]
                    if isinstance(node, ast.ImportFrom) and node.module
                    else None
                )
                if module:
                    used.add(module)

    return used

# ------------------ FREEZE / UNFREEZE ------------------

def freeze_file(path: Path, index):
    if is_protected(path):
        return

    rel = str(path)
    if rel in index:
        return

    target_dir = CAPS_FROZEN if CAP_IDENTIFIER in path.name else MODULES_FROZEN
    target_dir.mkdir(parents=True, exist_ok=True)

    frozen_path = target_dir / path.name
    shutil.move(str(path), frozen_path)

    index[rel] = {
        "original_path": rel,
        "frozen_path": str(frozen_path),
        "type": "capability" if CAP_IDENTIFIER in path.name else "module"
    }

    print(f"🧊 FROZEN: {rel}")

def unfreeze_file(entry, index):
    frozen = Path(entry["frozen_path"])
    original = Path(entry["original_path"])

    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(frozen), original)

    print(f"🔥 UNFROZEN: {original}")
    index.pop(entry["original_path"])

# ------------------ MAIN ------------------

def main():
    CAPS_FROZEN.mkdir(parents=True, exist_ok=True)
    MODULES_FROZEN.mkdir(parents=True, exist_ok=True)

    index = load_index()
    used_modules = discover_used_files()

    # UNFREEZE
    for entry in list(index.values()):
        name = Path(entry["original_path"]).stem
        if name in used_modules:
            unfreeze_file(entry, index)

    # FREEZE
    for py in ROOT.rglob("*.py"):
        if "frozen" in py.parts:
            continue
        if is_protected(py):
            continue

        if py.stem not in used_modules:
            freeze_file(py, index)

    save_index(index)

    print("Governança concluída com memória arquitetural.")

if __name__ == "__main__":
    main()