"""In-memory, short-lived authorization for the Jarvis Secure MCP Tunnel.

The owner provisions a high-entropy, one-use session secret locally. The secret is
never returned by this gateway or written to the audit log. Authentication
consumes the challenge atomically and exchanges the secret for a random bearer
token whose hash alone is retained in memory.

This module is deliberately independent of the MCP transport. Callers must
explicitly invoke authorize() before exposing a protected host capability.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable


class SessionError(PermissionError):
    """Authentication or authorization failed closed."""


ACCESS_CAPABILITIES = {
    "observer": frozenset(
        {
            "host.fs.list",
            "host.fs.read",
            "host.process.inspect",
            "host.system.diagnostics",
        }
    ),
    "developer": frozenset(
        {
            "host.fs.list",
            "host.fs.read",
            "host.process.inspect",
            "host.system.diagnostics",
            "host.command.git.read",
            "host.project.inspect",
        }
    ),
}
MIN_TTL_SECONDS = 30
MAX_TTL_SECONDS = 3600
CHALLENGE_TTL_SECONDS = 120
MAX_SECRET_LENGTH = 256
_SCRYPT_N = 2**14


@dataclass
class _Challenge:
    challenge_id: str
    secret_salt: bytes
    secret_digest: bytes
    device_id: str
    tunnel_instance_id: str
    access_level: str
    expires_at: float
    ttl_seconds: int
    attempts: int = 0
    consumed: bool = False


@dataclass
class _Session:
    token_digest: bytes
    device_id: str
    tunnel_instance_id: str
    access_level: str
    capabilities: frozenset[str]
    expires_at: float
    revoked: bool = False


class SessionAuthorizationGateway:
    """Thread-safe, process-local session registry with one-use challenges."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        max_attempts: int = 5,
        audit: Callable[[dict], None] | None = None,
    ) -> None:
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        self._clock = clock
        self._max_attempts = max_attempts
        self._audit = audit
        self._challenges: dict[str, _Challenge] = {}
        self._sessions: dict[bytes, _Session] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _validate_identity(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError(f"{name} must contain 1 to 256 characters")
        if any(ord(char) < 32 for char in value):
            raise ValueError(f"{name} contains control characters")
        return value.strip()

    @staticmethod
    def _same_identity(supplied: str, expected: str) -> bool:
        """Compare validated UTF-8 identities without leaking mismatch position."""
        return hmac.compare_digest(
            supplied.encode("utf-8"),
            expected.encode("utf-8"),
        )

    @staticmethod
    def _secret_digest(secret: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            secret.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=8,
            p=1,
            dklen=32,
        )

    def _record(self, event: str, **fields: str) -> None:
        if self._audit is None:
            return
        record = {"event": event, "timestamp": self._clock(), **fields}
        try:
            self._audit(record)
        except Exception:
            # Authorization must not be granted when its audit sink fails.
            raise SessionError("session audit sink unavailable") from None

    def open_session(
        self,
        *,
        secret: str,
        device_id: str,
        tunnel_instance_id: str,
        access_level: str = "observer",
        ttl_seconds: int = 900,
    ) -> dict[str, str | int]:
        """Provision a challenge on the host side; caller supplies its local secret."""
        if not isinstance(secret, str) or not 16 <= len(secret) <= MAX_SECRET_LENGTH:
            raise ValueError("session secret must contain 16 to 256 characters")
        if access_level not in ACCESS_CAPABILITIES:
            raise ValueError("unsupported access level")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
            raise ValueError("ttl_seconds must be an integer")
        if not MIN_TTL_SECONDS <= ttl_seconds <= MAX_TTL_SECONDS:
            raise ValueError(f"ttl_seconds must be between {MIN_TTL_SECONDS} and {MAX_TTL_SECONDS}")
        device_id = self._validate_identity(device_id, "device_id")
        tunnel_instance_id = self._validate_identity(tunnel_instance_id, "tunnel_instance_id")

        challenge_id = uuid.uuid4().hex
        salt = secrets.token_bytes(16)
        challenge = _Challenge(
            challenge_id=challenge_id,
            secret_salt=salt,
            secret_digest=self._secret_digest(secret, salt),
            device_id=device_id,
            tunnel_instance_id=tunnel_instance_id,
            access_level=access_level,
            expires_at=self._clock() + CHALLENGE_TTL_SECONDS,
            ttl_seconds=ttl_seconds,
        )
        with self._lock:
            self._purge_expired()
            self._challenges[challenge_id] = challenge
            self._record("challenge_opened", device_id=device_id, access_level=access_level)
        return {
            "challenge_id": challenge_id,
            "expires_in_seconds": CHALLENGE_TTL_SECONDS,
            "access_level": access_level,
            "device_id": device_id,
        }

    def authenticate(
        self,
        *,
        challenge_id: str,
        secret: str,
        device_id: str,
        tunnel_instance_id: str,
    ) -> dict[str, str | int]:
        """Consume one challenge and exchange the one-use secret for a session token."""
        if not isinstance(secret, str) or len(secret) > MAX_SECRET_LENGTH:
            raise SessionError("authentication failed")
        with self._lock:
            challenge = self._challenges.get(challenge_id)
            if challenge is None or challenge.consumed or challenge.expires_at <= self._clock():
                raise SessionError("challenge unavailable or expired")
            if challenge.attempts >= self._max_attempts:
                challenge.consumed = True
                raise SessionError("challenge attempt limit exceeded")
            challenge.attempts += 1
            try:
                supplied_device = self._validate_identity(device_id, "device_id")
                supplied_tunnel = self._validate_identity(tunnel_instance_id, "tunnel_instance_id")
            except ValueError:
                self._record("authentication_rejected", device_id=challenge.device_id)
                if challenge.attempts >= self._max_attempts:
                    challenge.consumed = True
                raise SessionError("authentication failed") from None

            valid_secret = hmac.compare_digest(
                self._secret_digest(secret, challenge.secret_salt),
                challenge.secret_digest,
            )
            valid_binding = (
                self._same_identity(supplied_device, challenge.device_id)
                and self._same_identity(supplied_tunnel, challenge.tunnel_instance_id)
            )
            if not (valid_secret and valid_binding):
                self._record("authentication_rejected", device_id=challenge.device_id)
                if challenge.attempts >= self._max_attempts:
                    challenge.consumed = True
                raise SessionError("authentication failed")

            challenge.consumed = True
            token = secrets.token_urlsafe(32)
            token_digest = hashlib.sha256(token.encode("ascii")).digest()
            # The authenticated session receives the owner-selected TTL, independently
            # bounded by open_session(). Challenge expiry does not extend the session.
            expires_at = self._clock() + challenge.ttl_seconds
            self._sessions[token_digest] = _Session(
                token_digest=token_digest,
                device_id=challenge.device_id,
                tunnel_instance_id=challenge.tunnel_instance_id,
                access_level=challenge.access_level,
                capabilities=ACCESS_CAPABILITIES[challenge.access_level],
                expires_at=expires_at,
            )
            self._record("session_authenticated", device_id=challenge.device_id, access_level=challenge.access_level)
            return {
                "authenticated": True,
                "session_token": token,
                "access_level": challenge.access_level,
                "expires_in_seconds": challenge.ttl_seconds,
            }

    def authorize(
        self,
        session_token: str,
        capability: str,
        *,
        device_id: str,
        tunnel_instance_id: str,
    ) -> bool:
        """Authorize only when the token, capability, device and tunnel all match."""
        if (
            not isinstance(session_token, str)
            or not session_token
            or not isinstance(capability, str)
            or not capability
        ):
            return False
        try:
            device_id = self._validate_identity(device_id, "device_id")
            tunnel_instance_id = self._validate_identity(tunnel_instance_id, "tunnel_instance_id")
        except ValueError:
            return False

        digest = hashlib.sha256(session_token.encode("utf-8")).digest()
        with self._lock:
            session = self._sessions.get(digest)
            if session is None or session.revoked or session.expires_at <= self._clock():
                return False
            if not self._same_identity(device_id, session.device_id):
                return False
            if not self._same_identity(tunnel_instance_id, session.tunnel_instance_id):
                return False
            return capability in session.capabilities

    def revoke(self, session_token: str) -> bool:
        if not isinstance(session_token, str) or not session_token:
            return False
        digest = hashlib.sha256(session_token.encode("utf-8")).digest()
        with self._lock:
            session = self._sessions.get(digest)
            if session is None or session.revoked:
                return False
            session.revoked = True
            self._record("session_revoked", device_id=session.device_id, access_level=session.access_level)
            return True

    def _purge_expired(self) -> None:
        now = self._clock()
        self._challenges = {
            key: value for key, value in self._challenges.items()
            if not value.consumed and value.expires_at > now
        }
        self._sessions = {
            key: value for key, value in self._sessions.items()
            if value.expires_at > now and not value.revoked
        }
