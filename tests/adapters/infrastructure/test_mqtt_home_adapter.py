import ssl
from types import SimpleNamespace

import pytest

from app.adapters.infrastructure import mqtt_home_adapter as adapter_module


class RecordingMqttClient:
    def __init__(self, client_id):
        self.client_id = client_id
        self.events = []

    def username_pw_set(self, username, password):
        self.events.append(("username_pw_set", username, password))

    def tls_set(self, **kwargs):
        self.events.append(("tls_set", kwargs))

    def tls_insecure_set(self, value):
        self.events.append(("tls_insecure_set", value))

    def connect(self, host, port, keepalive):
        self.events.append(("connect", host, port, keepalive))

    def loop_start(self):
        self.events.append(("loop_start",))


def install_fake_mqtt(monkeypatch, client_type=RecordingMqttClient):
    clients = []

    def create_client(client_id):
        client = client_type(client_id)
        clients.append(client)
        return client

    monkeypatch.setattr(adapter_module, "_MQTT_AVAILABLE", True)
    monkeypatch.setattr(
        adapter_module, "mqtt", SimpleNamespace(Client=create_client), raising=False
    )
    return clients


def test_tls_is_configured_with_required_verification_before_connect(monkeypatch):
    clients = install_fake_mqtt(monkeypatch)
    adapter = adapter_module.MqttHomeAdapter(
        host="broker.example.internal",
        port=8883,
        tls_enabled=True,
        tls_ca_certs="broker-ca.pem",
        tls_certfile="jarvis-client.pem",
        tls_keyfile="jarvis-client.key",
    )

    client = clients[0]
    assert [event[0] for event in client.events] == ["tls_set"]
    tls_options = client.events[0][1]
    assert tls_options == {
        "ca_certs": "broker-ca.pem",
        "certfile": "jarvis-client.pem",
        "keyfile": "jarvis-client.key",
        "cert_reqs": ssl.CERT_REQUIRED,
    }
    assert adapter.connect() is True
    assert [event[0] for event in client.events] == [
        "tls_set",
        "connect",
        "loop_start",
    ]
    assert not any(event[0] == "tls_insecure_set" for event in client.events)


def test_tls_uses_system_trust_store_when_ca_bundle_is_omitted(monkeypatch):
    clients = install_fake_mqtt(monkeypatch)
    adapter_module.MqttHomeAdapter(tls_enabled=True)

    tls_options = clients[0].events[0][1]
    assert tls_options["ca_certs"] is None
    assert tls_options["cert_reqs"] == ssl.CERT_REQUIRED


def test_plaintext_default_remains_backward_compatible(monkeypatch):
    clients = install_fake_mqtt(monkeypatch)
    adapter = adapter_module.MqttHomeAdapter(host="localhost", port=1883)

    assert adapter.connect() is True
    assert [event[0] for event in clients[0].events] == ["connect", "loop_start"]


def test_tls_client_certificate_and_key_must_be_paired(monkeypatch):
    install_fake_mqtt(monkeypatch)

    with pytest.raises(ValueError, match="provided together"):
        adapter_module.MqttHomeAdapter(tls_enabled=True, tls_certfile="client.pem")


def test_tls_material_is_rejected_when_tls_is_disabled():
    with pytest.raises(ValueError, match="require tls_enabled"):
        adapter_module.MqttHomeAdapter(tls_ca_certs="broker-ca.pem")


def test_tls_request_fails_closed_when_paho_is_unavailable(monkeypatch):
    monkeypatch.setattr(adapter_module, "_MQTT_AVAILABLE", False)

    with pytest.raises(RuntimeError, match="paho-mqtt"):
        adapter_module.MqttHomeAdapter(tls_enabled=True)


def test_tls_setup_error_aborts_initialization_before_connect(monkeypatch):
    class BrokenTlsClient(RecordingMqttClient):
        def tls_set(self, **kwargs):
            super().tls_set(**kwargs)
            raise RuntimeError("invalid CA bundle")

    clients = install_fake_mqtt(monkeypatch, BrokenTlsClient)

    with pytest.raises(RuntimeError, match="invalid CA bundle"):
        adapter_module.MqttHomeAdapter(tls_enabled=True)

    assert [event[0] for event in clients[0].events] == ["tls_set"]


def test_explicit_dry_run_does_not_open_a_plaintext_connection(monkeypatch):
    monkeypatch.setattr(adapter_module, "_MQTT_AVAILABLE", False)
    adapter = adapter_module.MqttHomeAdapter(dry_run=True, tls_enabled=True)

    assert adapter.connect() is True
    result = adapter.publish("home/light/set", "ON")
    assert result["success"] is True
    assert result["dry_run"] is True
