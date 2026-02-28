from pathlib import Path
import re

CAPS = Path("app/domain/capabilities")
USED = set()

for py in Path("app").rglob("*.py"):
    text = py.read_text(errors="ignore")
    for m in re.findall(r"cap_\d+", text):
        USED.add(m)

dead = []

for cap in CAPS.glob("cap_*.py"):
    if cap.stem not in USED:
        print("DEAD:", cap)
        dead.append(str(cap))
    else:
        print("USED:", cap)

Path("dead_caps.txt").write_text("\n".join(dead))
print(f"\nTotal DEAD: {len(dead)}")