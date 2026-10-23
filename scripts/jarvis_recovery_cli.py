"""Restore sealed healer checkpoints from a captured healer log."""
import argparse
import re
import sys
from pathlib import Path

from app.core.recovery_store import RecoveryError, RecoveryStore

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_PATTERN = re.compile(r"^RECOVERY_CHECKPOINT_ID=([0-9a-f-]{36})$", re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore JARVIS self-healing checkpoints")
    parser.add_argument("--restore-from-log", required=True, help="Healer output log containing checkpoint IDs")
    args = parser.parse_args()
    try:
        log = Path(args.restore_from_log).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Recovery log unavailable: {exc}", file=sys.stderr)
        return 2
    checkpoint_ids = list(dict.fromkeys(CHECKPOINT_PATTERN.findall(log)))
    if not checkpoint_ids:
        print("No sealed recovery checkpoints found.")
        return 0
    store = RecoveryStore(REPO_ROOT)
    success = True
    for checkpoint_id in reversed(checkpoint_ids):
        try:
            result = store.restore(checkpoint_id)
            print(f"Recovery {checkpoint_id}: success={result['success']} results={result['results']}")
            success = success and result["success"]
        except RecoveryError as exc:
            print(f"Recovery {checkpoint_id} failed: {exc}", file=sys.stderr)
            success = False
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
