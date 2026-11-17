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


def test_create_session_persists_only_pairing_digest_and_returns_high_entropy_code(
    tmp_path,
):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=_clock)

    created = gateway.create_session(profile="developer", ttl_minutes=30)
    persisted = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))

    assert len(created["pairing_code"]) >= 40
    assert created["pairing_code"] not in (tmp_path / "session.json").read_text(
        encoding="utf-8"
    )
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


def test_authenticated_session_expires_after_idle_lease(tmp_path):
    now = [_clock()]
    gateway = SessionAuthorizationGateway(
        tmp_path / "session.json", clock=lambda: now[0]
    )
    created = gateway.create_session(ttl_minutes=5)
    gateway.authenticate(created["pairing_code"])
    now[0] += timedelta(hours=24, minutes=1)

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
        gateway.authenticate("not-the-code")


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


def test_termux_developer_profile_grants_only_android_shell_capability(tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=_clock)
    created = gateway.create_session(profile="termux_developer")

    assert created["capabilities"] == ["android.shell.exec"]
    gateway.authenticate(created["pairing_code"])
    assert gateway.require("android.shell.exec")["profile"] == "termux_developer"
    with pytest.raises(SessionAuthorizationError, match="lacks capability"):
        gateway.require("host.fs.read")


def test_authenticated_session_survives_gateway_restart(tmp_path):
    path = tmp_path / "session.json"
    issuer = SessionAuthorizationGateway(path, clock=_clock)
    created = issuer.create_session(profile="termux_developer", ttl_minutes=5)
    issuer.authenticate(created["pairing_code"])

    restarted_gateway = SessionAuthorizationGateway(path, clock=_clock)

    authorization = restarted_gateway.require("android.shell.exec")

    assert authorization["session_id"] == created["session_id"]
    assert restarted_gateway.status()["authenticated"] is True


def test_authenticated_session_renews_idle_expiration_on_each_authorized_operation(
    tmp_path,
):
    now = [_clock()]
    path = tmp_path / "session.json"
    gateway = SessionAuthorizationGateway(path, clock=lambda: now[0])
    created = gateway.create_session(profile="termux_developer", ttl_minutes=5)
    gateway.authenticate(created["pairing_code"])
    now[0] += timedelta(minutes=4)

    gateway.require("android.shell.exec")

    state = json.loads(path.read_text(encoding="utf-8"))
    renewed_expiry = datetime.fromisoformat(state["expires_at"])
    assert datetime.fromisoformat(state["last_activity_at"]) == now[0]
    assert renewed_expiry > now[0] + timedelta(hours=23)


def test_authenticated_session_expires_only_after_idle_timeout_without_activity(
    tmp_path,
):
    now = [_clock()]
    path = tmp_path / "session.json"
    gateway = SessionAuthorizationGateway(path, clock=lambda: now[0])
    created = gateway.create_session(profile="termux_developer", ttl_minutes=5)
    gateway.authenticate(created["pairing_code"])
    now[0] += timedelta(hours=24, minutes=1)

    with pytest.raises(SessionAuthorizationError, match="expired"):
        gateway.require("android.shell.exec")


def test_legacy_authenticated_session_without_activity_field_is_upgraded_on_use(
    tmp_path,
):
    path = tmp_path / "session.json"
    gateway = SessionAuthorizationGateway(path, clock=_clock)
    created = gateway.create_session(profile="termux_developer", ttl_minutes=30)
    gateway.authenticate(created["pairing_code"])

    legacy_state = json.loads(path.read_text(encoding="utf-8"))
    legacy_state.pop("last_activity_at")
    legacy_state["expires_at"] = (
        datetime.fromisoformat(legacy_state["created_at"]) + timedelta(minutes=30)
    ).isoformat()
    path.write_text(json.dumps(legacy_state), encoding="utf-8")

    restarted_gateway = SessionAuthorizationGateway(path, clock=_clock)
    authorization = restarted_gateway.require("android.shell.exec")
    upgraded_state = json.loads(path.read_text(encoding="utf-8"))

    assert authorization["session_id"] == created["session_id"]
    assert upgraded_state["last_activity_at"] == _clock().isoformat()
    assert datetime.fromisoformat(upgraded_state["expires_at"]) > _clock() + timedelta(
        hours=23
    )


def test_termux_communication_profile_grants_only_chatgpt_prompt_capability(tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=_clock)
    created = gateway.create_session(profile="termux_communication")
    gateway.authenticate(created["pairing_code"])

    authorization = gateway.require("communication.chatgpt.prompt")

    assert authorization["profile"] == "termux_communication"
    with pytest.raises(SessionAuthorizationError, match="lacks capability"):
        gateway.require("android.shell.exec")


def test_termux_jarvis_profile_grants_shell_chatgpt_and_prospecting_capabilities(tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json", clock=_clock)
    created = gateway.create_session(profile="termux_jarvis")

    assert created["capabilities"] == [
        "android.shell.exec",
        "communication.chatgpt.prompt",
        "prospecting.cnpj.read",
        "prospecting.outreach.manage",
    ]
    gateway.authenticate(created["pairing_code"])

    assert gateway.require("android.shell.exec")["profile"] == "termux_jarvis"
    assert gateway.require("communication.chatgpt.prompt")["profile"] == "termux_jarvis"
    assert gateway.require("prospecting.cnpj.read")["profile"] == "termux_jarvis"
    assert gateway.require("prospecting.outreach.manage")["profile"] == "termux_jarvis"
    assert gateway.require("prospecting.demand.manage")["profile"] == "termux_jarvis"
    with pytest.raises(SessionAuthorizationError, match="lacks capability"):
        gateway.require("host.fs.read")
