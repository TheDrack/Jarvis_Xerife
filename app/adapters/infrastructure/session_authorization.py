"""Ephemeral, single-use pairing and capability authorization for remote host tools.

The local CLI issues a one-time high-entropy code. The MCP process stores only
its SHA-256 digest, consumes it once, and then checks the active session,
expiry, revocation and capability on every host operation. This is an
additional authorization layer; it does not replace Tailscale or transport TLS.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

SCHEMA_VERSION = 1
MAX_PAIRING_ATTEMPTS = 5
MIN_TTL_MINUTES = 5
MAX_TTL_MINUTES = 120

PROFILES: dict[str, frozenset[str]] = {
    "observer": frozenset({
        "host.fs.list",
        "host.fs.read",
        "host.command.profiles",
        "host.command.readonly",
    }),
    "developer": frozenset({
        "host.fs.list",
        "host.fs.read",
        "host.command.profiles",
        "host.command.readonly",
        "host.command.git_read",
        "host.command.inspect_d",
    }),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("stored timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def default_state_path() -> Path:
    configured = os.environ.get("JARVIS_SESSION_AUTH_STATE", "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return root / "Jarvis" / "session_authorization.json"
    return Path.home() / ".local" / "state" / "jarvis" / "session_authorization.json"


class SessionAuthorizationError(PermissionError):
    """Raised when a remote operation lacks a valid session capability."""


class SessionAuthorizationGateway:
    """Single-active-session gateway with one-time pairing and per-call checks."""

    def __init__(
        self,
        state_path: str | Path | None = None,
        *,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.state_path = Path(state_path) if state_path else default_state_path()
        self._clock = clock
        self._lock = threading.RLock()
        self._authenticated_session_id: str | None = None

    def create_session(self, *, profile: str = "observer", ttl_minutes: int = 30) -> dict[str, Any]:
        if not isinstance(profile, str) or profile not in PROFILES:
            raise ValueError(f"unsupported profile: {profile}")
        if isinstance(ttl_minutes, bool) or not isinstance(ttl_minutes, int):
            raise ValueError("ttl_minutes must be an integer")
        if not MIN_TTL_MINUTES <= ttl_minutes <= MAX_TTL_MINUTES:
            raise ValueError(
                f"ttl_minutes must be between {MIN_TTL_MINUTES} and {MAX_TTL_MINUTES}"
            )
        with self._lock, self._exclusive_file_lock():
            current = self._read_state(required=False)
            if current and not current.get("revoked_at"):
                expires = _parse_timestamp(current["expires_at"])
                if expires > self._now():
                    raise ValueError("an unexpired session exists; revoke it before creating another")
            code = secrets.token_urlsafe(32)
            now = self._now()
            session_id = uuid.uuid4().hex
            state = {
                "schema_version": SCHEMA_VERSION,
                "session_id": session_id,
                "profile": profile,
                "capabilities": sorted(PROFILES[profile]),
                "created_at": _timestamp(now),
                "expires_at": _timestamp(now + timedelta(minutes=ttl_minutes)),
                "secret_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
                "pairing_consumed_at": None,
                "failed_attempts": 0,
                "revoked_at": None,
            }
            self._write_state(state)
            return {
                "session_id": session_id,
                "profile": profile,
                "expires_at": state["expires_at"],
                "capabilities": state["capabilities"],
                "pairing_code": code,
            }

    def authenticate(self, pairing_code: str) -> dict[str, Any]:
        if not isinstance(pairing_code, str) or not pairing_code or len(pairing_code) > 256:
            raise SessionAuthorizationError("invalid or expired pairing code")
        with self._lock, self._exclusive_file_lock():
            state = self._read_state(required=True)
            self._validate_live_state(state)
            expected = state.get("secret_sha256")
            supplied = hashlib.sha256(pairing_code.encode("utf-8")).hexdigest()
            if (
                state.get("pairing_consumed_at")
                or not expected
                or state.get("failed_attempts", 0) >= MAX_PAIRING_ATTEMPTS
                or not hmac.compare_digest(expected, supplied)
            ):
                if not state.get("pairing_consumed_at") and state.get("failed_attempts", 0) < MAX_PAIRING_ATTEMPTS:
                    state["failed_attempts"] = int(state.get("failed_attempts", 0)) + 1
                    if state["failed_attempts"] >= MAX_PAIRING_ATTEMPTS:
                        state["secret_sha256"] = None
                    self._write_state(state)
                raise SessionAuthorizationError("invalid, consumed, or locked pairing code")
            state["pairing_consumed_at"] = _timestamp(self._now())
            state["secret_sha256"] = None
            self._write_state(state)
            self._authenticated_session_id = state["session_id"]
            return self._public_state(state, authenticated=True)

    def require(self, capability: str) -> dict[str, Any]:
        with self._lock, self._exclusive_file_lock():
            if not self._authenticated_session_id:
                raise SessionAuthorizationError("no authenticated remote session")
            state = self._read_state(required=True)
            self._validate_live_state(state)
            if state.get("session_id") != self._authenticated_session_id:
                self._authenticated_session_id = None
                raise SessionAuthorizationError("remote session was replaced")
            if not state.get("pairing_consumed_at"):
                self._authenticated_session_id = None
                raise SessionAuthorizationError("remote session is not paired")
            capabilities = state.get("capabilities", [])
            if capability not in capabilities:
                raise SessionAuthorizationError(f"session lacks capability: {capability}")
            return {
                "session_id": state["session_id"],
                "profile": state["profile"],
                "capability": capability,
                "expires_at": state["expires_at"],
            }

    def status(self) -> dict[str, Any]:
        with self._lock, self._exclusive_file_lock():
            state = self._read_state(required=False)
            if not state:
                return {"status": "no_session"}
            try:
                self._validate_live_state(state)
            except SessionAuthorizationError:
                return self._public_state(state, authenticated=False) | {"status": "inactive"}
            authenticated = (
                bool(state.get("pairing_consumed_at"))
                and self._authenticated_session_id == state.get("session_id")
            )
            status = "authenticated" if authenticated else (
                "paired_elsewhere_or_restart" if state.get("pairing_consumed_at") else "awaiting_pairing"
            )
            return self._public_state(state, authenticated=authenticated) | {"status": status}

    def revoke(self) -> dict[str, Any]:
        with self._lock, self._exclusive_file_lock():
            state = self._read_state(required=False)
            if not state:
                self._authenticated_session_id = None
                return {"status": "no_session"}
            if not state.get("revoked_at"):
                state["revoked_at"] = _timestamp(self._now())
                state["secret_sha256"] = None
                self._write_state(state)
            self._authenticated_session_id = None
            return {"status": "revoked", "session_id": state["session_id"]}

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise SessionAuthorizationError("authorization clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _validate_live_state(self, state: dict[str, Any]) -> None:
        if state.get("schema_version") != SCHEMA_VERSION:
            raise SessionAuthorizationError("unsupported session state version")
        profile = state.get("profile")
        if (
            not isinstance(profile, str)
            or profile not in PROFILES
            or state.get("capabilities") != sorted(PROFILES[profile])
        ):
            raise SessionAuthorizationError("session capability state is invalid")
        session_id = state.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise SessionAuthorizationError("session identity is invalid")
        attempts = state.get("failed_attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not 0 <= attempts <= MAX_PAIRING_ATTEMPTS:
            raise SessionAuthorizationError("pairing attempt state is invalid")
        consumed_at = state.get("pairing_consumed_at")
        secret_digest = state.get("secret_sha256")
        if consumed_at:
            try:
                _parse_timestamp(consumed_at)
            except (TypeError, ValueError):
                raise SessionAuthorizationError("pairing consumption timestamp is invalid") from None
            if secret_digest is not None:
                raise SessionAuthorizationError("consumed pairing secret was not cleared")
        elif (
            not isinstance(secret_digest, str)
            or len(secret_digest) != 64
            or any(character not in "0123456789abcdef" for character in secret_digest)
        ):
            raise SessionAuthorizationError("pairing digest state is invalid")
        try:
            created_at = _parse_timestamp(state["created_at"])
            expires_at = _parse_timestamp(state["expires_at"])
        except (KeyError, TypeError, ValueError):
            raise SessionAuthorizationError("session timestamps are invalid") from None
        now = self._now()
        if created_at > now or expires_at <= created_at or expires_at - created_at > timedelta(minutes=MAX_TTL_MINUTES):
            raise SessionAuthorizationError("session time window is invalid")
        if state.get("revoked_at"):
            raise SessionAuthorizationError("remote session was revoked")
        if expires_at <= now:
            raise SessionAuthorizationError("remote session expired")

    @contextmanager
    def _exclusive_file_lock(self) -> Iterator[None]:
        """Serialize state transitions across the CLI and MCP server processes."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_path.with_name(self.state_path.name + ".lock")
        with lock_path.open("a+b") as lock_file:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\\0")
                lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_state(self, *, required: bool) -> dict[str, Any] | None:
        try:
            raw = self.state_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            if required:
                raise SessionAuthorizationError("no session has been issued") from None
            return None
        try:
            state = json.loads(raw)
            if not isinstance(state, dict):
                raise ValueError("session state must be an object")
            return state
        except (json.JSONDecodeError, ValueError) as exc:
            raise SessionAuthorizationError(
                f"session state is invalid ({type(exc).__name__})"
            ) from None

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.state_path.parent.chmod(0o700)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.state_path.name}.", suffix=".tmp", dir=self.state_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.state_path)
            if os.name != "nt":
                self.state_path.chmod(0o600)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    @staticmethod
    def _public_state(state: dict[str, Any], *, authenticated: bool) -> dict[str, Any]:
        return {
            "session_id": state["session_id"],
            "profile": state["profile"],
            "capabilities": list(state.get("capabilities", [])),
            "expires_at": state["expires_at"],
            "authenticated": authenticated,
            "revoked": bool(state.get("revoked_at")),
            "pairing_consumed": bool(state.get("pairing_consumed_at")),
        }



# Shared by all MCP tool modules inside this server process.
SESSION_GATEWAY = SessionAuthorizationGateway()

def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Issue or revoke a local one-time Jarvis remote session."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser("create", help="issue a one-time pairing code locally")
    create.add_argument("--profile", choices=sorted(PROFILES), default="observer")
    create.add_argument("--ttl-minutes", type=int, default=30)
    subparsers.add_parser("status", help="show local session metadata")
    subparsers.add_parser("revoke", help="revoke the active session immediately")
    args = parser.parse_args(argv)
    gateway = SessionAuthorizationGateway()
    try:
        if args.action == "create":
            result = gateway.create_session(profile=args.profile, ttl_minutes=args.ttl_minutes)
            print("PAIRING CODE (shown once; do not reuse):")
            print(result.pop("pairing_code"))
            print(json.dumps(result, indent=2))
        elif args.action == "status":
            print(json.dumps(gateway.status(), indent=2))
        else:
            print(json.dumps(gateway.revoke(), indent=2))
    except (ValueError, SessionAuthorizationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
