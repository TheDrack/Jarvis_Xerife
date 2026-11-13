"""Tests for ephemeral remote-session pairing and capability authorization."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.infrastructure.session_authorization import (
    MAX_PAIRING_ATTEMPTS,
    SessionAuthorizationError,
    SessionAuthorizationGateway,
)


def _clock():
    return datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_create_session_persists_only_pairing_digest_and_returns_high_entropy_code(tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=_clock)

    created = gateway.create_session(profile="developer", ttl_minutes=30)
    persisted = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))

    assert len(created["pairing_code"]) >= 40
    assert created["pairing_code"] not in (tmp_path / "session.json").read_text(encoding="utf-8")
    assert persisted["secret_sha256"]
    assert persisted["secret_sha256"] != created["pairing_code"]
    assert "host.command.git_read" in created["capabilities"]


def test_pairing_code_is_single_use_and_capabilities_are_server_assigned(tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=_clock)
    created = gateway.create_session(profile="observer")
    paired = gateway.authenticate(created["pairing_code"])

    assert paired["authenticated"] is True
    assert gateway.require("host.fs.read")["session_id"] == created["session_id"]
    with pytest.raises(SessionAuthorizationError, match="consumed"):
        gateway.authenticate(created["pairing_code"])
    with pytest.raises(SessionAuthorizationError, match="lacks capability"):
        gateway.require("host.command.git_read")


def test_wrong_pairing_code_is_rate_limited_and_never_authenticates(tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=_clock)
    gateway.create_session()
    for _ in range(MAX_PAIRING_ATTEMPTS):
        with pytest.raises(SessionAuthorizationError):
            gateway.authenticate("wrong-code")
    with pytest.raises(SessionAuthorizationError, match="locked"):
        gateway.authenticate("wrong-code")
    assert gateway.status()["authenticated"] is False
    assert gateway.status()["status"] == "pairing_locked"


def test_expired_session_is_denied(tmp_path):
    now = [_clock()]
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=lambda: now[0])
    created = gateway.create_session(ttl_minutes=5)
    gateway.authenticate(created["pairing_code"])
    now[0] += timedelta(minutes=6)

    with pytest.raises(SessionAuthorizationError, match="expired"):
        gateway.require("host.fs.list")
    assert gateway.status()["status"] == "inactive"


def test_revocation_is_observed_by_an_already_authenticated_gateway(tmp_path):
    path = tmp_path / "session.json"
    owner = SessionAuthorizationGateway(path, clock=_clock)
    client = SessionAuthorizationGateway(path, clock=_clock)
    created = owner.create_session()
    client.authenticate(created["pairing_code"])

    owner.revoke()

    with pytest.raises(SessionAuthorizationError, match="revoked"):
        client.require("host.fs.list")


def test_only_one_unexpired_session_can_be_issued_without_revocation(tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=_clock)
    gateway.create_session()
    with pytest.raises(ValueError, match="revoke"):
        gateway.create_session(profile="developer")


@pytest.mark.parametrize("ttl", [0, 4, 121, True])
def test_invalid_ttl_is_rejected(tmp_path, ttl):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=_clock)
    with pytest.raises(ValueError):
        gateway.create_session(ttl_minutes=ttl)


def test_corrupt_state_fails_closed(tmp_path):
    path = tmp_path / "session.json"
    path.write_text("{not-json", encoding="utf-8")
    gateway = SessionAuthorizationGateway(path, clock=_clock)

    with pytest.raises(SessionAuthorizationError, match="invalid"):
        gateway.require("host.fs.list")


def test_capability_tampering_in_state_fails_closed(tmp_path):
    path = tmp_path / "session.json"
    gateway = SessionAuthorizationGateway(path, clock=_clock)
    gateway.create_session(profile="observer")
    state = json.loads(path.read_text(encoding="utf-8"))
    state["capabilities"].append("host.command.git_read")
    path.write_text(json.dumps(state), encoding="utf-8")
    client = SessionAuthorizationGateway(path, clock=_clock)

    with pytest.raises(SessionAuthorizationError, match="capability state"):
        client.authenticate("not-the-code")


def test_status_handles_structurally_corrupt_state_without_crashing(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    gateway = SessionAuthorizationGateway(path, clock=_clock)

    assert gateway.status()["status"] == "inactive"
