"""Conservative local checkpoint/restore primitives for Jarvis.

This module does not execute commands or mutate external services. Callers
checkpoint before a mutation and seal afterwards. Restore refuses to overwrite
post-seal changes and never deletes files created by the operation.
"""
from __future__ import annotations
import hashlib, json, os, stat, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

class RecoveryError(RuntimeError):
    """Base exception for recovery-store errors."""

def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class RecoveryStore:
    """Content-addressed snapshots with an append-only hash-chained event journal."""

    def __init__(self, root: str | Path, storage_dir: str | Path | None = None) -> None:
        self.root = Path(root).resolve()
        configured = storage_dir or os.environ.get("JARVIS_RECOVERY_DIR")
        self.storage_dir = Path(configured).expanduser().resolve() if configured else self.root / ".jarvis-recovery"
        self.objects_dir = self.storage_dir / "objects"
        self.checkpoints_dir = self.storage_dir / "checkpoints"
        self.journal_path = self.storage_dir / "events.jsonl"
        self._lock = threading.RLock()
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, value: str | Path) -> tuple[Path, str]:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        if candidate.is_symlink():
            raise RecoveryError(f"Symlink target is not supported: {value}")
        resolved = candidate.resolve(strict=False)
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as exc:
            raise RecoveryError(f"Target escapes recovery root: {value}") from exc
        if relative == Path("."):
            raise RecoveryError("Recovery root is not a file target")
        return resolved, relative.as_posix()

    def _store_object(self, content: bytes) -> str:
        digest = _digest(content)
        target = self.objects_dir / digest
        if not target.exists():
            temporary = self.objects_dir / f".{digest}.{uuid.uuid4().hex}.tmp"
            with temporary.open("xb") as handle:
                handle.write(content); handle.flush(); os.fsync(handle.fileno())
            try:
                os.replace(temporary, target)
            except OSError:
                temporary.unlink(missing_ok=True)
                if not target.exists():
                    raise
        return digest

    def _manifest(self, checkpoint_id: str) -> dict[str, Any]:
        try:
            uuid.UUID(checkpoint_id)
            path = self.checkpoints_dir / f"{checkpoint_id}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            raise RecoveryError(f"Checkpoint missing or invalid: {checkpoint_id}") from exc
        if data.get("checkpoint_id") != checkpoint_id:
            raise RecoveryError("Checkpoint identity mismatch")
        return data

    def checkpoint(self, paths: Iterable[str | Path], *, reason: str, run_id: str | None = None) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("reason must be non-empty")
        targets = {}
        for item in paths:
            path, relative = self._resolve(item)
            targets[relative] = path
        if not targets:
            raise ValueError("At least one target path is required")
        entries = []
        for relative, path in sorted(targets.items()):
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise RecoveryError(f"Only regular files are supported: {relative}")
            exists = path.is_file()
            entry = {"path": relative, "existed_before": exists, "before_sha256": None, "before_mode": None}
            if exists:
                entry["before_sha256"] = self._store_object(path.read_bytes())
                entry["before_mode"] = stat.S_IMODE(path.stat().st_mode)
            entries.append(entry)
        checkpoint_id = str(uuid.uuid4())
        manifest = {"schema_version": 1, "checkpoint_id": checkpoint_id, "run_id": run_id,
                    "reason": reason, "created_at": _now(), "root": str(self.root),
                    "sealed_at": None, "files": entries}
        self._write_manifest(manifest)
        self._append_event({"event_id": str(uuid.uuid4()), "event_type": "checkpoint_created",
                            "checkpoint_id": checkpoint_id, "run_id": run_id, "reason": reason,
                            "created_at": _now(), "file_count": len(entries)})
        return manifest

    def seal(self, checkpoint_id: str) -> dict[str, Any]:
        manifest = self._manifest(checkpoint_id)
        if manifest.get("sealed_at"):
            raise RecoveryError("Checkpoint already sealed")
        for entry in manifest["files"]:
            path, _ = self._resolve(entry["path"])
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise RecoveryError(f"Cannot seal non-regular file: {entry['path']}")
            entry["after_exists"] = path.is_file()
            entry["after_sha256"] = _digest(path.read_bytes()) if path.is_file() else None
            entry["after_mode"] = stat.S_IMODE(path.stat().st_mode) if path.is_file() else None
        manifest["sealed_at"] = _now()
        self._write_manifest(manifest)
        self._append_event({"event_id": str(uuid.uuid4()), "event_type": "checkpoint_sealed",
                            "checkpoint_id": checkpoint_id, "run_id": manifest.get("run_id"), "created_at": _now()})
        return manifest

    def restore(self, checkpoint_id: str) -> dict[str, Any]:
        manifest = self._manifest(checkpoint_id)
        if not manifest.get("sealed_at"):
            raise RecoveryError("Checkpoint must be sealed before restore")
        results = []
        for entry in manifest["files"]:
            relative = entry["path"]
            path, _ = self._resolve(relative)
            if path.is_symlink() or (path.exists() and not path.is_file()):
                results.append({"path": relative, "status": "conflict", "reason": "not_regular_file"}); continue
            exists = path.is_file()
            current = _digest(path.read_bytes()) if exists else None
            if not entry["existed_before"]:
                if exists:
                    results.append({"path": relative, "status": "requires_authorization",
                                    "reason": "would_delete_file_created_by_operation"})
                else:
                    results.append({"path": relative, "status": "unchanged"})
                continue
            if exists != bool(entry.get("after_exists")) or (exists and current != entry.get("after_sha256")):
                results.append({"path": relative, "status": "conflict", "reason": "state_changed_after_seal"}); continue
            digest = entry.get("before_sha256")
            object_path = self.objects_dir / str(digest)
            try:
                original = object_path.read_bytes()
            except OSError:
                results.append({"path": relative, "status": "conflict", "reason": "snapshot_missing"}); continue
            if not digest or _digest(original) != digest:
                results.append({"path": relative, "status": "conflict", "reason": "snapshot_hash_mismatch"}); continue
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.restore")
            try:
                with temporary.open("xb") as handle:
                    handle.write(original); handle.flush(); os.fsync(handle.fileno())
                os.chmod(temporary, int(entry.get("before_mode") or 0o600))
                os.replace(temporary, path)
                results.append({"path": relative, "status": "restored"})
            finally:
                temporary.unlink(missing_ok=True)
        success = all(r["status"] in {"restored", "unchanged"} for r in results)
        outcome = {"checkpoint_id": checkpoint_id, "success": success, "results": results, "completed_at": _now()}
        self._append_event({"event_id": str(uuid.uuid4()), "event_type": "restore_completed",
                            "checkpoint_id": checkpoint_id, "run_id": manifest.get("run_id"),
                            "success": success, "results": results, "created_at": outcome["completed_at"]})
        return outcome

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        target = self.checkpoints_dir / f"{manifest['checkpoint_id']}.json"
        temporary = target.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target)

    def _append_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            previous = None
            if self.journal_path.exists():
                with self.journal_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        if line.strip():
                            previous = json.loads(line).get("event_hash")
            payload = dict(event)
            payload["previous_event_hash"] = previous
            payload["event_hash"] = _digest(_canonical(payload))
            descriptor = os.open(self.journal_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, _canonical(payload) + b"\n"); os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def verify_journal(self) -> dict[str, Any]:
        previous, count = None, 0
        if not self.journal_path.exists():
            return {"valid": True, "events": 0, "last_hash": None}
        with self.journal_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    return {"valid": False, "events": count, "line": line_number, "reason": "invalid_json"}
                claimed = event.pop("event_hash", None)
                if event.get("previous_event_hash") != previous:
                    return {"valid": False, "events": count, "line": line_number, "reason": "broken_hash_link"}
                if claimed != _digest(_canonical(event)):
                    return {"valid": False, "events": count, "line": line_number, "reason": "event_hash_mismatch"}
                previous, count = claimed, count + 1
        return {"valid": True, "events": count, "last_hash": previous}
