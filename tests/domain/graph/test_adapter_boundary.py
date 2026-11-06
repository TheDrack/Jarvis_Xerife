from __future__ import annotations

import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3] / "app"
RESOLVER = Path("app/domain/graph/resolver.py")
CONSTRUCTION = re.compile(r"Node\(\s*type\s*=\s*NodeType\.(PERSON|ORG)\b")


def test_only_the_resolver_constructs_person_or_org_nodes() -> None:
    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT.parent)
        if relative == RESOLVER:
            continue
        if CONSTRUCTION.search(path.read_text(encoding="utf-8")):
            offenders.append(str(relative))

    assert offenders == []


def test_resolver_does_construct_them() -> None:
    source = (APP_ROOT.parent / RESOLVER).read_text(encoding="utf-8")

    assert CONSTRUCTION.search(source)
