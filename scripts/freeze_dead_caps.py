# scripts/freeze_dead_caps.py
from pathlib import Path

dead = []
with open("dead_caps.txt") as f:
    dead = [line.strip() for line in f if line.strip()]

target = Path("app/domain/capabilities/_frozen")
target.mkdir(exist_ok=True)

for cap in dead:
    src = Path(cap)
    if src.exists():
        src.rename(target / src.name)
        print("FROZEN:", src)