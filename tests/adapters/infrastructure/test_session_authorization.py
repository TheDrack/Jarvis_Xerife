"""Tests for the temporary Jarvis Session Bridge authorization gateway."""
from __future__ import annotations

import time

import pytest

from app.adapters.infrastructure.session_authorization import (
    SessionAuthorizationGateway,
    SessionError,
)


def test_session_secret_is_single_use_and_returns_scoped_token():
    gateway = SessionAuthorizationGateway(clock=lambda: 100.0)
    challenge = gateway.open_session(
        secret="one-time-session-secret",
        device_id="DESKTOP-HPJ82UA",
        tunnel_instance_id="tunnel-1",
        access_level="observer",
        ttl_seconds=300,
    )

    session = gateway.authenticate(
        challenge_id=challenge["challenge_id"],
        secret="one-time-session-secret",
        device_id="DESKTOP-HPJ82UA",
        tunnel_instance_id="tunnel-1",
    )

    assert session["authenticated"] is True
    assert session["access_level"] == "observer"
    assert gateway.authorize(session["session_token"], "host.fs.read") is True
    assert gateway.authorize(session["session_token"], "host.process.inspect") is False


def test_challenge_cannot_be_replayed():
    gateway = SessionAuthorizationGateway(clock=lambda: 100.0)
    challenge = gateway.open_session(
        secret="one-time-session-secret",
        device_id="desktop",
        tunnel_instance_id="tunnel",
        access_level="observer",
    )
    gateway.authenticate(
        challenge_id=challenge["challenge_id"],
        secret="one-time-session-secret",
        device_id="desktop",
        tunnel_instance_id="tunnel",
    )
    with pytest.raises(SessionError):
        gateway.authenticate(
            challenge_id=challenge["challenge_id"],
            secret="one-time-session-secret",
            device_id="desktop",
            tunnel_instance_id="tunnel",
        )


@pytest.mark.parametrize(
    "field,value",
    [("device_id", "other-device"), ("tunnel_instance_id", "other-tunnel")],
)
def test_authentication_is_bound_to_device_and_tunnel(field, value):
    gateway = SessionAuthorizationGateway(clock=lambda: 100.0)
    challenge = gateway.open_session(
        secret="one-time-session-secret",
        device_id="desktop",
        tunnel_instance_id="tunnel",
        access_level="observer",
    )
    kwargs = {
        "challenge_id": challenge["challenge_id"],
        "secret": "one-time-session-secret",
        "device_id": "desktop",
        "tunnel_instance_id": "tunnel",
    }
    kwargs[field] = value
    with pytest.raises(SessionError):
        gateway.authenticate(**kwargs)


def test_session_expiry_and_revocation_revoke_capabilities():
    now = [100.0]
    gateway = SessionAuthorizationGateway(clock=lambda: now[0])
    challenge = gateway.open_session(
        secret="one-time-session-secret",
        device_id="desktop",
        tunnel_instance_id="tunnel",
        access_level="developer",
        ttl_seconds=30,
    )
    session = gateway.authenticate(
        challenge_id=challenge["challenge_id"],
        secret="one-time-session-secret",
        device_id="desktop",
        tunnel_instance_id="tunnel",
    )
    token = session["session_token"]
    assert gateway.authorize(token, "host.command.git.read") is True
    assert gateway.revoke(token) is True
    assert gateway.authorize(token, "host.command.git.read") is False

    challenge = gateway.open_session(
        secret="another-one-time-secret",
        device_id="desktop",
        tunnel_instance_id="tunnel",
        access_level="observer",
        ttl_seconds=30,
    )
    session = gateway.authenticate(
        challenge_id=challenge["challenge_id"],
        secret="another-one-time-secret",
        device_id="desktop",
        tunnel_instance_id="tunnel",
    )
    now[0] = 131.0
    assert gateway.authorize(session["session_token"], "host.fs.read") is False


def test_invalid_secret_does_not_consume_challenge_and_is_rate_limited():
    gateway = SessionAuthorizationGateway(clock=lambda: 100.0, max_attempts=2)
    challenge = gateway.open_session(
        secret="correct-secret-value",
        device_id="desktop",
        tunnel_instance_id="tunnel",
    )
    for _ in range(2):
        with pytest.raises(SessionError):
            gateway.authenticate(
                challenge_id=challenge["challenge_id"],
                secret="wrong-secret-value",
                device_id="desktop",
                tunnel_instance_id="tunnel",
            )
    with pytest.raises(SessionError):
        gateway.authenticate(
            challenge_id=challenge["challenge_id"],
            secret="correct-secret-value",
            device_id="desktop",
            tunnel_instance_id="tunnel",
        )


def test_unknown_capabilities_and_invalid_levels_fail_closed():
    gateway = SessionAuthorizationGateway(clock=lambda: 100.0)
    with pytest.raises(ValueError):
        gateway.open_session(
            secret="one-time-session-secret",
            device_id="desktop",
            tunnel_instance_id="tunnel",
            access_level="administrator",
        )
