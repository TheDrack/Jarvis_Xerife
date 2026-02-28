from pathlib import Path
import re

CAPS = Path("app/domain/capabilities")

imports = set()
for py in Path("app").rglob("*.py"):
    text = py.read_text(errors="ignore")
    for m in re.findall(r"cap_\d+", text):
        imports.add(m)

for cap in CAPS.glob("cap_*.py"):
    if cap.stem not in imports:
        print("DEAD:", cap)
    else:
        print("USED:", cap)